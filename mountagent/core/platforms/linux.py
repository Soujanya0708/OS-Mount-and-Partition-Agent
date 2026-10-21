"""
linux.py - Linux backend: lsblk, losetup, blkid and the mount()/umount2() system calls (via ctypes).
"""

import ctypes
import ctypes.util
import json
import os
import posixpath
import re
from pathlib import PurePath
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ... import config
from ..runner import ToolError
from ..session import MountRecord
from .base import Platform

# Flags from <sys/mount.h>
MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4

_FLAG_NAMES = [(MS_RDONLY, "MS_RDONLY"), (MS_NOSUID, "MS_NOSUID"), (MS_NODEV, "MS_NODEV")]

_libc = None
if config.IS_LINUX:
    try:
        _libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
    except OSError:
        _libc = None


def _flag_names(flags: int) -> str:
    return "|".join(name for bit, name in _FLAG_NAMES if flags & bit) or "0"


def ensure_safe_mount_point(path: str) -> str:
    norm = posixpath.normpath(path)
    if not any(norm.startswith(prefix + "/") for prefix in config.SAFE_MOUNT_PREFIXES):
        allowed = " or ".join(config.SAFE_MOUNT_PREFIXES)
        raise ToolError(f"refusing to use '{path}': mount points must be inside {allowed}")
    return norm


class LinuxPlatform(Platform):
    name = "linux"
    description = ("Linux: lsblk lists devices, image files are attached to /dev/loopN with losetup, "
                   "filesystems are mounted with the mount(2) syscall under /mnt/agent/<name>. "
                   "Block devices look like /dev/sdb1.")

    def is_device(self, source: str) -> bool:
        return source.startswith("/dev/")

    # ------------------------------------------------------------ lsblk

    def list_block_devices(self) -> List[Dict[str, Any]]:
        res = self.r.run(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL,MODEL"])
        try:
            return json.loads(res.stdout).get("blockdevices", [])
        except json.JSONDecodeError:
            raise ToolError("could not parse lsblk output")

    def partitions_of(self, device: str) -> List[Dict[str, Any]]:
        """Partitions exposed on a device (e.g. /dev/loop0p1 after losetup --partscan)."""
        res = self.r.run(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE", device], check=False)
        try:
            devices = json.loads(res.stdout).get("blockdevices", [])
        except json.JSONDecodeError:
            return []
        return devices[0].get("children", []) if devices else []

    # ------------------------------------------------------------ losetup

    def list_attached_images(self) -> List[Dict[str, Any]]:
        res = self.r.run(["losetup", "-J", "-l"], check=False)
        if not res.stdout.strip():
            return []
        try:
            return json.loads(res.stdout).get("loopdevices", [])
        except json.JSONDecodeError:
            raise ToolError("could not parse losetup output")

    def attach_loop(self, image: str, read_only: bool) -> str:
        """losetup --find --show: map an image file to the next free /dev/loopN."""
        cmd = ["losetup", "--find", "--show", "--partscan"]
        if read_only:
            cmd.append("--read-only")
        cmd.append(image)
        return self.r.run(cmd).stdout.strip()

    def detach_loop(self, device: str):
        self.r.run(["losetup", "-d", device])

    # ------------------------------------------------------------ format detection

    def detect_filesystem(self, path: str) -> str:
        """blkid first (the standard tool), then read the signature bytes ourselves."""
        fstype = self.r.run(["blkid", "-o", "value", "-s", "TYPE", path], check=False).stdout.strip()
        if fstype:
            return fstype
        if not self.is_device(path):
            fstype = self.sniff(path)
        return fstype or "auto"

    # ------------------------------------------------------------ mount / umount

    def mount(self, source: str, read_only: bool, mount_point: Optional[str],
              partition: Optional[int], taken: Iterable[str]) -> Tuple[MountRecord, str]:
        # Validate the target before touching anything, so a refusal never leaves a loop device behind
        target = ensure_safe_mount_point(mount_point or self._default_mount_point(source, taken))
        fstype = self.detect_filesystem(source)
        loop_dev = None
        device = source

        if self.is_device(source):
            if partition:
                # /dev/sdb + 1 -> /dev/sdb1, /dev/nvme0n1 + 1 -> /dev/nvme0n1p1
                device = f"{source}p{partition}" if source[-1].isdigit() else f"{source}{partition}"
                fstype = self.detect_filesystem(device)
        else:
            loop_dev = self.attach_loop(source, read_only)
            device = loop_dev
            parts = self.partitions_of(loop_dev)
            if parts:
                # Partitioned disk image: pick the requested partition, else the first with a filesystem
                if partition:
                    if partition > len(parts):
                        self.detach_loop(loop_dev)
                        raise ToolError(f"image has {len(parts)} partition(s), no partition {partition}")
                    chosen = parts[partition - 1]
                else:
                    chosen = next((p for p in parts if p.get("fstype")), parts[0])
                device = "/dev/" + chosen["name"]
                fstype = chosen.get("fstype") or self.detect_filesystem(device)

        try:
            method = self._mount_fs(device, target, fstype, read_only)
        except ToolError:
            if loop_dev:
                self.detach_loop(loop_dev)
            raise

        record = MountRecord(source=source, device=device, mount_point=target, filesystem=fstype,
                             read_only=read_only, kind="loop" if loop_dev else "device", loop_device=loop_dev)
        return record, method

    def unmount(self, target: str, record: Optional[MountRecord]) -> Dict[str, Any]:
        mount_point = record.mount_point if record else target
        if not mount_point.startswith("/"):
            raise ToolError(f"nothing named '{target}' was mounted in this session; give the full mount point")
        mount_point = ensure_safe_mount_point(mount_point)

        self._umount_fs(mount_point)
        released = None
        if record and record.loop_device:
            self.detach_loop(record.loop_device)
            released = record.loop_device
        return {"mount_point": mount_point, "released": released}

    def _mount_fs(self, source: str, target: str, fstype: str, read_only: bool) -> str:
        """
        Mount via the mount(2) syscall:
            int mount(const char *source, const char *target, const char *fstype,
                      unsigned long flags, const void *data);
        Falls back to mount(8) when the type is unknown or the syscall is rejected.
        """
        r = self.r
        flags = MS_NOSUID | MS_NODEV | (MS_RDONLY if read_only else 0)
        r.note(f"mkdir -p {target}")
        if not r.dry_run:
            os.makedirs(target, exist_ok=True)

        if fstype != "auto" and (_libc is not None or r.dry_run):
            r.note(f'mount("{source}", "{target}", "{fstype}", {_flag_names(flags)}, NULL)')
            if r.dry_run:
                r.sim.mark_mounted(source, target)
                return "mount(2) syscall"
            rc = _libc.mount(source.encode(), target.encode(), fstype.encode(), ctypes.c_ulong(flags), None)
            if rc == 0:
                return "mount(2) syscall"
            r.note(f"# mount(2) failed: {os.strerror(ctypes.get_errno())} -> falling back to mount(8)")

        opts = ",".join(["ro" if read_only else "rw", "nosuid", "nodev"])
        cmd = ["mount", "-o", opts]
        if fstype != "auto":
            cmd += ["-t", fstype]
        r.run(cmd + [source, target])
        return "mount(8)"

    def _umount_fs(self, target: str):
        """umount2(2) syscall, falling back to umount(8)."""
        r = self.r
        if _libc is not None or r.dry_run:
            r.note(f'umount2("{target}", 0)')
            if r.dry_run or _libc.umount2(target.encode(), 0) == 0:
                return
            r.note(f"# umount2 failed: {os.strerror(ctypes.get_errno())} -> falling back to umount(8)")
        r.run(["umount", target])

    def _default_mount_point(self, source: str, taken: Iterable[str]) -> str:
        stem = re.sub(r"\s+", "_", PurePath(source).stem) or "disk"
        base = posixpath.join(config.MOUNT_ROOT, stem)
        taken = set(taken)
        candidate, n = base, 2
        while candidate in taken or (not self.r.dry_run and os.path.ismount(candidate)):
            candidate, n = f"{base}-{n}", n + 1
        return candidate
