"""
OS backends. Each one implements the same Platform interface with that OS's native tools:

  linux    lsblk, losetup, blkid, mount(2)/umount2(2)
  windows  Get-Disk/Get-Partition/Get-Volume, Mount-DiskImage, Add-PartitionAccessPath
"""

from ..runner import Runner
from .base import Platform
from .linux import LinuxPlatform
from .windows import WindowsPlatform

PLATFORMS = {"linux": LinuxPlatform, "windows": WindowsPlatform}


def get_platform(name: str, runner: Runner) -> Platform:
    return PLATFORMS[name](runner)
