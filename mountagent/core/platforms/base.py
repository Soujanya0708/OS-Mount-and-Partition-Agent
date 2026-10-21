"""
base.py - The interface every OS backend implements, plus the parts that are the same everywhere.
"""

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .. import fsdetect
from ..runner import Runner, ToolError
from ..session import MountRecord


class Platform:
    name = "base"
    # Shown in tool descriptions / the system prompt so the LLM knows what it is driving
    description = ""

    def __init__(self, runner: Runner):
        self.r = runner

    # ------------------------------------------------------------ OS-specific

    def is_device(self, source: str) -> bool:
        raise NotImplementedError

    def list_block_devices(self) -> List[Dict[str, Any]]:
        """lsblk-shaped tree: [{name, size, type, fstype, mountpoint, label, children: [...]}]"""
        raise NotImplementedError

    def list_attached_images(self) -> List[Dict[str, Any]]:
        """[{name, back-file, ro}] - loop devices on Linux, mounted disk images on Windows."""
        raise NotImplementedError

    def detect_filesystem(self, path: str) -> str:
        raise NotImplementedError

    def mount(self, source: str, read_only: bool, mount_point: Optional[str],
              partition: Optional[int], taken: Iterable[str]) -> Tuple[MountRecord, str]:
        """Returns the new mount and the method used."""
        raise NotImplementedError

    def unmount(self, target: str, record: Optional[MountRecord]) -> Dict[str, Any]:
        """Returns {"mount_point": ..., "released": loop device / image / partition or None}."""
        raise NotImplementedError

    # ------------------------------------------------------------ shared

    def sniff(self, path: str) -> Optional[str]:
        """Read the filesystem signature straight from the file's first sectors."""
        self.r.note(f"read signature bytes of {path}")
        if self.r.dry_run:
            return self.r.sim.guess_fs(path)
        return fsdetect.sniff(path)

    def list_dir(self, path: str, limit: int) -> List[Dict[str, Any]]:
        self.r.note(f"list directory {path}")
        if self.r.dry_run:
            return self.r.sim.listing(path)[:limit]
        try:
            with os.scandir(path) as it:
                entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                return [{"name": e.name, "is_dir": e.is_dir(),
                         "size": 0 if e.is_dir() else e.stat(follow_symlinks=False).st_size}
                        for e in entries[:limit]]
        except FileNotFoundError:
            raise ToolError(f"'{path}' does not exist")
        except PermissionError:
            raise ToolError(f"permission denied reading '{path}'")


def human_size(n: Optional[float]) -> str:
    if not n:
        return ""
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit in ("B", "K") else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}P"
