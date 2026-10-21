"""
simulator.py - Fake outputs for dry-run mode.
Lets the terminal be demonstrated on any machine, for either platform,
while still printing the exact commands and syscalls that would run.
"""

import json
from pathlib import PurePath, PureWindowsPath
from typing import Dict, List

SAMPLE_DISKS = [
    {"name": "sda", "size": "50G", "type": "disk", "fstype": None, "mountpoint": None,
     "label": None, "model": "VBOX HARDDISK", "children": [
         {"name": "sda1", "size": "1M", "type": "part", "fstype": None, "mountpoint": None, "label": None},
         {"name": "sda2", "size": "513M", "type": "part", "fstype": "vfat", "mountpoint": "/boot/efi", "label": None},
         {"name": "sda3", "size": "49.5G", "type": "part", "fstype": "ext4", "mountpoint": "/", "label": None},
     ]},
    {"name": "sdb", "size": "16G", "type": "disk", "fstype": None, "mountpoint": None,
     "label": None, "model": "USB Flash Disk", "children": [
         {"name": "sdb1", "size": "16G", "type": "part", "fstype": "vfat", "mountpoint": None, "label": "USB"},
     ]},
    {"name": "sr0", "size": "1024M", "type": "rom", "fstype": None, "mountpoint": None,
     "label": None, "model": "CD-ROM"},
]

WIN_DISKS = [
    {"Number": 0, "FriendlyName": "NVMe SSD", "BusType": "NVMe", "Size": 512110190592},
    {"Number": 1, "FriendlyName": "USB Flash Disk", "BusType": "USB", "Size": 16008609792},
]
WIN_PARTITIONS = [
    {"DiskNumber": 0, "PartitionNumber": 1, "DriveLetter": None, "Size": 272629760, "Type": "System",
     "FileSystem": "FAT32", "Label": ""},
    {"DiskNumber": 0, "PartitionNumber": 2, "DriveLetter": None, "Size": 16777216, "Type": "Reserved",
     "FileSystem": None, "Label": None},
    {"DiskNumber": 0, "PartitionNumber": 3, "DriveLetter": "C", "Size": 510678532096, "Type": "Basic",
     "FileSystem": "NTFS", "Label": "Windows"},
    {"DiskNumber": 1, "PartitionNumber": 1, "DriveLetter": None, "Size": 16007561216, "Type": "Basic",
     "FileSystem": "FAT32", "Label": "USB"},
]

FS_BY_EXTENSION = {".iso": "iso9660", ".img": "ext4", ".raw": "ext4", ".bin": "iso9660",
                   ".vhd": "vhd", ".vhdx": "vhdx"}

SAMPLE_ISO_LISTING = [
    ("boot", True), ("casper", True), ("dists", True), ("EFI", True), ("install", True),
    ("pool", True), ("boot.catalog", False), ("md5sum.txt", False), ("README.diskdefines", False),
]


def _path(p: str):
    return PureWindowsPath(p) if "\\" in p or ":" in p else PurePath(p)


class Simulator:
    """Keeps just enough state (attached loops / images) to make dry-runs consistent."""

    def __init__(self):
        self.loops: Dict[str, Dict] = {}
        self.win_images: Dict[str, str] = {}       # image path -> drive letter
        self.win_partition_letters: Dict[str, str] = {}

    # ------------------------------------------------------------ Linux commands

    def respond(self, cmd: List[str]) -> str:
        prog, args = cmd[0], cmd[1:]

        if prog == "lsblk":
            target = next((a for a in args if a.startswith("/dev/")), None)
            if target:
                name = target.rsplit("/", 1)[-1]
                loop = self.loops.get(target, {})
                return json.dumps({"blockdevices": [
                    {"name": name, "size": "4.7G", "type": "loop", "fstype": loop.get("fstype")}]})
            loops = [{"name": dev.rsplit("/", 1)[-1], "size": "4.7G", "type": "loop",
                      "fstype": info["fstype"], "mountpoint": info.get("mountpoint"), "label": None}
                     for dev, info in self.loops.items()]
            return json.dumps({"blockdevices": SAMPLE_DISKS + loops})

        if prog == "losetup":
            if "--find" in args:
                dev = f"/dev/loop{len(self.loops)}"
                backing = args[-1]
                self.loops[dev] = {"back-file": backing, "ro": "--read-only" in args,
                                   "fstype": self.guess_fs(backing)}
                return dev + "\n"
            if "-d" in args:
                self.loops.pop(args[args.index("-d") + 1], None)
                return ""
            if "-J" in args:
                return json.dumps({"loopdevices": [
                    {"name": dev, "back-file": info["back-file"], "ro": info["ro"]}
                    for dev, info in self.loops.items()]})

        if prog == "blkid":
            path = args[-1]
            if path in self.loops:
                return (self.loops[path]["fstype"] or "") + "\n"
            return (self.guess_fs(path) or "") + "\n"

        return ""

    def mark_mounted(self, device: str, mount_point: str):
        if device in self.loops:
            self.loops[device]["mountpoint"] = mount_point

    # ------------------------------------------------------------ Windows PowerShell

    def powershell(self, key: str, **a) -> str:
        if key == "disks":
            parts = [dict(p) for p in WIN_PARTITIONS]
            for p in parts:
                p["DriveLetter"] = self.win_partition_letters.get(
                    f"{p['DiskNumber']}:{p['PartitionNumber']}", p["DriveLetter"])
            optical = [{"DriveLetter": letter, "FileSystem": "CDFS", "FileSystemLabel": _path(img).stem.upper(),
                        "Size": 4700000000} for img, letter in self.win_images.items()]
            return json.dumps({"disks": WIN_DISKS, "partitions": parts, "optical": optical})

        if key == "images":
            return json.dumps([{"name": f"{letter}:", "back-file": img, "ro": True}
                               for img, letter in self.win_images.items()])

        if key == "mount_image":
            letter = next(l for l in "DEFGHIJKLMNOPQRSTUVWXYZ"
                          if l not in self.win_images.values() and l not in self.win_partition_letters.values())
            self.win_images[a["path"]] = letter
            fs = "CDFS" if a["storage"] == "ISO" else "NTFS"
            return json.dumps({"device": f"\\\\.\\CDROM{len(self.win_images) - 1}",
                               "volumes": [{"DriveLetter": letter, "FileSystem": fs, "FileSystemLabel": ""}]})

        if key == "unmount_image":
            self.win_images.pop(a["path"], None)
            return ""

        if key == "mount_partition":
            self.win_partition_letters[f"{a['disk']}:{a['part']}"] = "E"
            return json.dumps({"letter": "E", "fs": "FAT32", "new": True})

        if key == "unmount_partition":
            self.win_partition_letters.pop(f"{a['disk']}:{a['part']}", None)
            return ""

        if key == "resolve_letter":
            for img, letter in self.win_images.items():
                if letter == a["letter"]:
                    return json.dumps({"image": img})
            protected = a["letter"] == "C"
            return json.dumps({"disk": 0 if protected else 1, "part": 3 if protected else 1, "protected": protected})

        if key == "volume_fs":
            return json.dumps({"fs": "FAT32"})

        return ""

    # ------------------------------------------------------------ shared

    @staticmethod
    def guess_fs(path: str):
        return FS_BY_EXTENSION.get(_path(path).suffix.lower())

    @staticmethod
    def listing(path: str):
        return [{"name": n, "is_dir": d, "size": 0 if d else 2048} for n, d in SAMPLE_ISO_LISTING]
