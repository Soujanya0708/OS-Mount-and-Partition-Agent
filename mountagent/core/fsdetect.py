"""
fsdetect.py - Identify a filesystem by reading its on-disk signature (magic bytes).
Pure Python, so it works the same on Linux and Windows and needs no privileges.
"""

from typing import Optional

ISO_OFFSET = 0x8001          # "CD001" in the first volume descriptor (sector 16 + 1)
EXT_MAGIC_OFFSET = 1080      # superblock at 1024, s_magic at +0x38
EXT_COMPAT_OFFSET = 1024 + 0x5C
EXT_INCOMPAT_OFFSET = 1024 + 0x60


def sniff(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            head = f.read(ISO_OFFSET + 8)
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(size - 512, 0))
            tail = f.read(512)
    except OSError:
        return None

    if head[ISO_OFFSET:ISO_OFFSET + 5] == b"CD001":
        return "iso9660"
    if head[ISO_OFFSET:ISO_OFFSET + 5] in (b"BEA01", b"NSR02", b"NSR03"):
        return "udf"
    if head[:8] == b"vhdxfile":
        return "vhdx"
    if tail[:8] == b"conectix":
        return "vhd"
    if head[:4] == b"hsqs":
        return "squashfs"
    if head[EXT_MAGIC_OFFSET:EXT_MAGIC_OFFSET + 2] == b"\x53\xef":
        compat = int.from_bytes(head[EXT_COMPAT_OFFSET:EXT_COMPAT_OFFSET + 4], "little")
        incompat = int.from_bytes(head[EXT_INCOMPAT_OFFSET:EXT_INCOMPAT_OFFSET + 4], "little")
        if incompat & (0x40 | 0x80 | 0x200):   # extents / 64bit / flex_bg
            return "ext4"
        return "ext3" if compat & 0x4 else "ext2"   # has_journal
    if head[3:11] == b"NTFS    ":
        return "ntfs"
    if head[3:11] == b"EXFAT   ":
        return "exfat"
    if head[82:87] == b"FAT32" or head[54:59] in (b"FAT12", b"FAT16"):
        return "vfat"
    if head[510:512] == b"\x55\xaa":
        # Boot signature but no filesystem in sector 0: a whole-disk image with a partition table
        return "gpt-disk" if head[512:520] == b"EFI PART" else "mbr-disk"
    return None
