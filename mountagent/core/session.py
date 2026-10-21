"""
session.py - Remembers what this terminal session mounted,
so follow-ups like "unmount it" or "unmount ubuntu" can be resolved.
"""

from dataclasses import dataclass, asdict
from pathlib import PurePath, PureWindowsPath
from typing import List, Optional


@dataclass
class MountRecord:
    source: str
    device: str
    mount_point: str
    filesystem: str
    read_only: bool
    kind: str                         # "loop" / "device" (Linux), "image" / "partition" (Windows)
    loop_device: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _norm(s: Optional[str]) -> Optional[str]:
    return s.rstrip("/\\").lower() if s else s


class Session:
    def __init__(self):
        self.mounts: List[MountRecord] = []

    def add(self, record: MountRecord):
        self.mounts.append(record)

    def remove(self, record: MountRecord):
        self.mounts.remove(record)

    def last(self) -> Optional[MountRecord]:
        return self.mounts[-1] if self.mounts else None

    def find(self, ref: Optional[str]) -> Optional[MountRecord]:
        """Match by mount point, source path, device, drive letter, or bare name ("ubuntu")."""
        if not ref or ref.lower() in ("it", "that", "this", "last"):
            return self.last()
        ref = _norm(ref)
        for rec in reversed(self.mounts):
            src = PureWindowsPath(rec.source) if "\\" in rec.source else PurePath(rec.source)
            names = {rec.mount_point, rec.source, rec.device, rec.loop_device,
                     src.name, src.stem, PurePath(rec.mount_point).name}
            if ref in {_norm(n) for n in names if n}:
                return rec
        return None

    def mount_points(self):
        return {m.mount_point for m in self.mounts}
