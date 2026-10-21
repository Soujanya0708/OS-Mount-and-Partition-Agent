"""
heuristic.py - Offline natural-language parser.
Maps a sentence to a plan of tool calls with regex rules, so the terminal works
with no LLM at all (lab machines without internet). Understands Linux and Windows
style paths and device names.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..core.session import Session

IMAGE_EXT = r"(?:iso|img|raw|bin|qcow2|vhdx|vhd|dmg)"

_QUOTED = re.compile(r"[\"'`]([^\"'`]+)[\"'`]")
_IMAGE = re.compile(rf"(?<![\w/.~\\:-])((?:[A-Za-z]:)?(?:~|\.{{1,2}})?[\w./~\\-]*\.{IMAGE_EXT})\b", re.I)
_DEVICE = re.compile(r"(/dev/[\w/-]+)")
_ABS_PATH = re.compile(r"(?<![\w.:\\])(/(?:[\w.-]+/?)*)")
_DRIVE = re.compile(r"(?<![\w\\/])([A-Za-z]:\\?)(?=[\s.,?!]|$)")
_DISK = re.compile(r"\bdisk\s*#?(\d+)(?:\s*p(?:art(?:ition)?)?\s*#?(\d+))?\b", re.I)
_MOUNT_AT = re.compile(r"\b(?:at|on|to|into|under)\s+(/[\w./-]+|[A-Za-z]:\\?(?=[\s.,?!]|$))", re.I)
_PARTITION = re.compile(r"\bpartition\s*(?:#|no\.?|number)?\s*(\d+)", re.I)


def _has(text: str, *words: str) -> bool:
    return any(re.search(rf"\b{w}\b", text) for w in words)


@dataclass
class Plan:
    thought: str
    steps: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)


def find_paths(prompt: str) -> List[str]:
    """All path-like tokens in order of appearance (quoted strings first)."""
    found = [m.group(1) for m in _QUOTED.finditer(prompt)]
    hits = []
    for rx in (_IMAGE, _DEVICE, _ABS_PATH, _DRIVE):
        hits += [(m.start(), m.group(1).rstrip(".,")) for m in rx.finditer(prompt)]
    hits += [(m.start(), f"disk{m.group(1)}" + (f"p{m.group(2)}" if m.group(2) else ""))
             for m in _DISK.finditer(prompt)]
    for _, p in sorted(hits):
        if p not in found and not any(p in f for f in found):
            found.append(p)
    return found


def _is_mount_location(path: str, session: Session) -> bool:
    return bool(path.startswith(("/mnt", "/media")) or _DRIVE.fullmatch(path) or session.find(path))


def parse(prompt: str, session: Session) -> Optional[Plan]:
    p = prompt.lower()
    paths = find_paths(prompt)
    at = _MOUNT_AT.search(prompt)
    mount_point = at.group(1) if at else None
    sources = [x for x in paths if x != mount_point]
    source = sources[0] if sources else None

    # Unmount / eject
    if _has(p, "unmount", "umount", "eject", "detach", "dismount"):
        target = source
        if not target:
            words = re.findall(r"[\w.-]+", p)
            target = next((w for w in words if session.find(w)), None) or "it"
        return Plan("User wants to unmount something and release its loop device / disk image.",
                    [("unmount", {"target": target})])

    # Attached images / loop devices
    if _has(p, "loop", "loops", "losetup", "loopback", "attached") and not _has(p, "mount"):
        return Plan("User wants to see which image files are attached as devices.",
                    [("list_attached_images", {})])

    # Filesystem identification
    if source and _has(p, "inspect", "format", "formatted", "filesystem", "identify", "detect", "fstype", "type"):
        return Plan(f"User wants the filesystem format of '{source}'.",
                    [("inspect_filesystem", {"path": source})])

    # Browse an already-mounted location
    wants_files = _has(p, "ls", "dir", "files", "contents", "inside", "browse", "what's in", "whats in")
    if wants_files and source and _is_mount_location(source, session) and not _has(p, "mount"):
        return Plan(f"User wants to see the files in '{source}'.",
                    [("list_files", {"path": source})])

    # Mount
    is_image = bool(source and re.search(rf"\.{IMAGE_EXT}$", source, re.I))
    if _has(p, "mount", "attach", "open", "access") or (is_image and wants_files):
        if not source:
            return None
        args: Dict[str, Any] = {"source": source,
                                "read_only": not _has(p, "rw", "read-write", "read write", "writable", "write")}
        if mount_point:
            args["mount_point"] = mount_point
        part = _PARTITION.search(prompt)
        if part and not re.search(r"p\d+$", source):
            args["partition"] = int(part.group(1))
        steps = [("mount", args)]
        if wants_files or is_image:
            steps.append(("list_files", {"path": "@mount_point"}))
        mode = "read-only" if args["read_only"] else "read-write"
        kind = "image file" if is_image else "partition/device"
        return Plan(f"User wants to mount '{source}' ({kind}, {mode}).", steps)

    # Device / partition listing
    if _has(p, "list", "show", "lsblk", "devices", "disks", "drives", "partitions", "partition", "storage", "volumes"):
        return Plan("User wants an overview of disks and partitions.",
                    [("list_block_devices", {})])

    return None
