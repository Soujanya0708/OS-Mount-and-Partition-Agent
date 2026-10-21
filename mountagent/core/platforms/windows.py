"""
windows.py - Windows backend, driven through PowerShell's Storage module.

  Linux idea           Windows equivalent used here
  ---------------      ----------------------------------------------
  lsblk                Get-Disk / Get-Partition / Get-Volume
  losetup + mount()    Mount-DiskImage (ISO, VHD, VHDX) -> drive letter
  mount /dev/sdb1      Add-PartitionAccessPath -AssignDriveLetter (admin)
  umount               Dismount-DiskImage / Remove-PartitionAccessPath
  blkid                signature bytes, or Get-Volume.FileSystem
"""

import re
from pathlib import PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..runner import ToolError, as_list, ps_quote
from ..session import MountRecord
from .base import Platform, human_size

DISK_RE = re.compile(r"^disk\s*(\d+)(?:\s*p(?:art(?:ition)?)?\s*(\d+))?$", re.I)
DRIVE_RE = re.compile(r"^([A-Za-z]):\\?$")

# Filesystems Windows cannot open without third-party drivers
LINUX_ONLY_FS = {"ext2", "ext3", "ext4", "squashfs", "xfs", "btrfs"}


class WindowsPlatform(Platform):
    name = "windows"
    description = ("Windows: devices are listed with Get-Disk/Get-Partition/Get-Volume, ISO/VHD/VHDX images "
                   "are attached with Mount-DiskImage and get a drive letter (e.g. D:\\) instead of a /mnt "
                   "folder. Physical partitions are named like disk1p2 (disk 1, partition 2) and mounting "
                   "them needs an administrator terminal. Windows cannot read ext4 images.")

    def is_device(self, source: str) -> bool:
        return bool(DISK_RE.match(source.strip()))

    # ------------------------------------------------------------ listing

    def list_block_devices(self) -> List[Dict[str, Any]]:
        data = self.r.powershell(
            "$v = @{}; Get-Volume | ForEach-Object { if ($_.Path) { $v[$_.Path] = $_ } }; "
            "$d = @(Get-Disk | Select-Object Number, FriendlyName, BusType, Size); "
            "$p = @(Get-Partition | ForEach-Object { $vol = $_ | Get-Volume -ErrorAction SilentlyContinue; "
            "  [pscustomobject]@{ DiskNumber = $_.DiskNumber; PartitionNumber = $_.PartitionNumber; "
            "  DriveLetter = $(if ($_.DriveLetter -and [int]$_.DriveLetter) { [string]$_.DriveLetter } else { $null }); "
            "  Size = $_.Size; Type = [string]$_.Type; FileSystem = $vol.FileSystem; Label = $vol.FileSystemLabel } }); "
            "$o = @(Get-Volume | Where-Object { $_.DriveType -eq 'CD-ROM' -and $_.DriveLetter } | "
            "  Select-Object @{n='DriveLetter';e={[string]$_.DriveLetter}}, FileSystem, FileSystemLabel, Size); "
            "@{ disks = $d; partitions = $p; optical = $o } | ConvertTo-Json -Depth 4 -Compress",
            display="Get-Disk; Get-Partition | Get-Volume", sim_key="disks") or {}

        parts = as_list(data.get("partitions"))
        devices = []
        for disk in as_list(data.get("disks")):
            n = disk["Number"]
            children = [{
                "name": f"disk{n}p{p['PartitionNumber']}",
                "size": human_size(p.get("Size")),
                "type": "part" if p.get("Type") in ("Basic", "IFS") else f"part ({p.get('Type')})",
                "fstype": p.get("FileSystem"),
                "mountpoint": f"{p['DriveLetter']}:\\" if p.get("DriveLetter") else None,
                "label": p.get("Label") or None,
            } for p in parts if p["DiskNumber"] == n]
            devices.append({"name": f"disk{n}", "size": human_size(disk.get("Size")), "type": "disk",
                            "fstype": None, "mountpoint": None,
                            "model": f"{disk.get('FriendlyName')} ({disk.get('BusType')})",
                            "children": children})
        for vol in as_list(data.get("optical")):
            devices.append({"name": f"cdrom ({vol['DriveLetter']}:)", "size": human_size(vol.get("Size")),
                            "type": "rom", "fstype": vol.get("FileSystem"),
                            "mountpoint": f"{vol['DriveLetter']}:\\", "label": vol.get("FileSystemLabel")})
        return devices

    def list_attached_images(self) -> List[Dict[str, Any]]:
        data = self.r.powershell(
            "$out = @(); "
            "Get-Volume | Where-Object { $_.DriveType -eq 'CD-ROM' -and $_.DriveLetter } | ForEach-Object { "
            "  $img = $_ | Get-DiskImage -ErrorAction SilentlyContinue; "
            "  if ($img) { $out += [pscustomobject]@{ name = \"$($_.DriveLetter):\"; 'back-file' = $img.ImagePath; ro = $true } } }; "
            "Get-Disk | Where-Object { $_.BusType -eq 'File Backed Virtual' } | ForEach-Object { "
            "  $out += [pscustomobject]@{ name = \"disk$($_.Number)\"; 'back-file' = $_.Location; ro = $_.IsReadOnly } }; "
            "ConvertTo-Json -InputObject $out -Compress",
            display="Get-Volume | Get-DiskImage; Get-Disk (File Backed Virtual)", sim_key="images")
        return as_list(data)

    # ------------------------------------------------------------ format detection

    def detect_filesystem(self, path: str) -> str:
        if self.is_device(path):
            disk, part = self._parse_device(path, None)
            data = self.r.powershell(
                f"@{{ fs = (Get-Partition -DiskNumber {disk} -PartitionNumber {part} | "
                f"Get-Volume -ErrorAction SilentlyContinue).FileSystem }} | ConvertTo-Json -Compress",
                display=f"Get-Partition -DiskNumber {disk} -PartitionNumber {part} | Get-Volume",
                sim_key="volume_fs") or {}
            return data.get("fs") or "unknown"
        return self.sniff(path) or "unknown"

    # ------------------------------------------------------------ mount

    def mount(self, source: str, read_only: bool, mount_point: Optional[str],
              partition: Optional[int], taken: Iterable[str]) -> Tuple[MountRecord, str]:
        if mount_point and not DRIVE_RE.match(mount_point):
            raise ToolError("on Windows a mounted image gets a drive letter (like D:\\); "
                            "mounting into a folder is not supported - leave the mount point out")
        if self.is_device(source):
            return self._mount_partition(source, partition)
        return self._mount_image(source, read_only, partition)

    def _mount_image(self, path: str, read_only: bool, partition: Optional[int]) -> Tuple[MountRecord, str]:
        name = PureWindowsPath(path).name
        fs = self.detect_filesystem(path)
        ext = PureWindowsPath(path).suffix.lower()

        if fs in LINUX_ONLY_FS:
            raise ToolError(f"{name} contains an {fs} filesystem, which Windows cannot read. "
                            "Mount it on Linux (or inside WSL) instead.")
        if fs in ("mbr-disk", "gpt-disk") and ext not in (".vhd", ".vhdx"):
            raise ToolError(f"{name} is a raw whole-disk image; Windows can only attach ISO, VHD and VHDX. "
                            "Convert it first, e.g.  qemu-img convert -O vhdx " f"{name} disk.vhdx")

        storage = "VHDX" if ext == ".vhdx" or fs == "vhdx" else "VHD" if ext == ".vhd" or fs == "vhd" else "ISO"
        read_only = read_only or storage == "ISO"     # optical images are always read-only
        access = "ReadOnly" if read_only else "ReadWrite"
        p = ps_quote(path)
        volumes_expr = ("$img | Get-Volume" if storage == "ISO"
                        else "$img | Get-Disk | Get-Partition | Get-Volume -ErrorAction SilentlyContinue")

        data = self.r.powershell(
            f"$existing = Get-DiskImage -ImagePath {p} -ErrorAction SilentlyContinue; "
            f"if ($existing -and $existing.Attached) {{ throw 'that image is already mounted - unmount it first' }}; "
            f"Mount-DiskImage -ImagePath {p} -StorageType {storage} -Access {access} | Out-Null; "
            f"$img = Get-DiskImage -ImagePath {p}; $vols = @(); "
            f"for ($i = 0; $i -lt 20 -and $vols.Count -eq 0; $i++) {{ "
            f"  $vols = @({volumes_expr} | Where-Object {{ $_.DriveLetter }}); if ($vols.Count -eq 0) {{ Start-Sleep -Milliseconds 250 }} }}; "
            f"@{{ device = $img.DevicePath; volumes = @($vols | Select-Object "
            f"@{{n='DriveLetter';e={{[string]$_.DriveLetter}}}}, FileSystem, FileSystemLabel) }} | ConvertTo-Json -Depth 3 -Compress",
            display=f"Mount-DiskImage -ImagePath {p} -StorageType {storage} -Access {access}",
            sim_key="mount_image", path=path, storage=storage) or {}

        volumes = as_list(data.get("volumes"))
        if not volumes:
            self._dismount_image(path)
            raise ToolError(f"Windows attached {name} but found no filesystem it can read "
                            "(it reads NTFS, FAT, exFAT, ISO9660 and UDF)")
        if partition and partition > len(volumes):
            self._dismount_image(path)
            raise ToolError(f"{name} has {len(volumes)} readable volume(s), no partition {partition}")
        vol = volumes[(partition or 1) - 1]

        record = MountRecord(source=path, device=data.get("device") or name,
                             mount_point=f"{vol['DriveLetter']}:\\",
                             filesystem=vol.get("FileSystem") or fs, read_only=read_only, kind="image")
        return record, "Mount-DiskImage"

    def _mount_partition(self, source: str, partition: Optional[int]) -> Tuple[MountRecord, str]:
        disk, part = self._parse_device(source, partition)
        data = self.r.powershell(
            f"$p = Get-Partition -DiskNumber {disk} -PartitionNumber {part}; "
            f"if ($p.IsBoot -or $p.IsSystem) {{ throw 'refusing to touch the Windows boot/system partition' }}; "
            f"$new = $false; "
            f"if (-not ($p.DriveLetter -and [int]$p.DriveLetter)) {{ "
            f"  Add-PartitionAccessPath -DiskNumber {disk} -PartitionNumber {part} -AssignDriveLetter; $new = $true; "
            f"  $p = Get-Partition -DiskNumber {disk} -PartitionNumber {part} }}; "
            f"$v = $p | Get-Volume -ErrorAction SilentlyContinue; "
            f"@{{ letter = [string]$p.DriveLetter; fs = $v.FileSystem; new = $new }} | ConvertTo-Json -Compress",
            display=f"Add-PartitionAccessPath -DiskNumber {disk} -PartitionNumber {part} -AssignDriveLetter",
            sim_key="mount_partition", disk=disk, part=part) or {}

        if not data.get("letter"):
            raise ToolError("Windows did not assign a drive letter (is the partition formatted with NTFS/FAT/exFAT?)")
        if not data.get("new"):
            raise ToolError(f"disk{disk}p{part} is already mounted at {data['letter']}:\\")

        record = MountRecord(source=f"disk{disk}p{part}", device=f"disk{disk}p{part}",
                             mount_point=f"{data['letter']}:\\", filesystem=data.get("fs") or "unknown",
                             read_only=False, kind="partition")
        return record, "Add-PartitionAccessPath"

    # ------------------------------------------------------------ unmount

    def unmount(self, target: str, record: Optional[MountRecord]) -> Dict[str, Any]:
        if record:
            if record.kind == "image":
                self._dismount_image(record.source)
                return {"mount_point": record.mount_point, "released": record.source}
            disk, part = self._parse_device(record.device, None)
            self._remove_letter(disk, part, record.mount_point)
            return {"mount_point": record.mount_point, "released": record.device}

        target = target.strip().strip("'\"")
        if PureWindowsPath(target).suffix.lower() in (".iso", ".img", ".vhd", ".vhdx", ".bin"):
            self._dismount_image(target)
            return {"mount_point": None, "released": target}

        drive = DRIVE_RE.match(target)
        if not drive:
            raise ToolError(f"don't know what '{target}' is; give a drive letter (D:) or an image path")
        letter = drive.group(1).upper()
        info = self.r.powershell(
            f"$img = Get-Volume -DriveLetter {letter} | Get-DiskImage -ErrorAction SilentlyContinue; "
            f"if ($img) {{ @{{ image = $img.ImagePath }} | ConvertTo-Json -Compress }} else {{ "
            f"  $p = Get-Partition -DriveLetter {letter}; "
            f"  @{{ disk = $p.DiskNumber; part = $p.PartitionNumber; protected = [bool]($p.IsBoot -or $p.IsSystem) }} "
            f"  | ConvertTo-Json -Compress }}",
            display=f"Get-Volume -DriveLetter {letter} | Get-DiskImage", sim_key="resolve_letter",
            letter=letter) or {}

        if info.get("image"):
            self._dismount_image(info["image"])
            return {"mount_point": f"{letter}:\\", "released": info["image"]}
        if info.get("protected"):
            raise ToolError(f"refusing to unmount {letter}: - it holds Windows itself")
        self._remove_letter(info["disk"], info["part"], f"{letter}:\\")
        return {"mount_point": f"{letter}:\\", "released": f"disk{info['disk']}p{info['part']}"}

    def _dismount_image(self, path: str):
        p = ps_quote(path)
        self.r.powershell(f"Dismount-DiskImage -ImagePath {p} | Out-Null",
                          display=f"Dismount-DiskImage -ImagePath {p}", sim_key="unmount_image", path=path)

    def _remove_letter(self, disk: int, part: int, access_path: str):
        self.r.powershell(
            f"$p = Get-Partition -DiskNumber {disk} -PartitionNumber {part}; "
            f"if ($p.IsBoot -or $p.IsSystem) {{ throw 'refusing to touch the Windows boot/system partition' }}; "
            f"Remove-PartitionAccessPath -DiskNumber {disk} -PartitionNumber {part} -AccessPath {ps_quote(access_path)}",
            display=f"Remove-PartitionAccessPath -DiskNumber {disk} -PartitionNumber {part} -AccessPath {access_path}",
            sim_key="unmount_partition", disk=disk, part=part)

    @staticmethod
    def _parse_device(source: str, partition: Optional[int]) -> Tuple[int, int]:
        m = DISK_RE.match(source.strip())
        if not m:
            raise ToolError(f"'{source}' is not a Windows partition name (expected e.g. disk1p2)")
        part = int(m.group(2)) if m.group(2) else partition
        if not part:
            raise ToolError(f"say which partition of disk {m.group(1)} to mount, e.g. disk{m.group(1)}p1")
        return int(m.group(1)), part
