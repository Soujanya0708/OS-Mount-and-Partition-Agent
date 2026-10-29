"""
tools.py - The tools the agent can call, with JSON schemas for LLM backends,
and the ToolBox that executes them through the current OS backend (Linux or Windows).
Every tool returns a dict with "ok": True/False so results can be fed straight back to an LLM.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from .. import config
from ..core.platforms import Platform
from ..core.runner import ToolError
from ..core.session import Session

# Tools that change system state; the terminal asks for confirmation before running them
MUTATING_TOOLS = {"mount", "unmount"}

TOOL_SPECS = [
    {
        "name": "list_block_devices",
        "description": "List disks, partitions, their filesystems and where they are mounted (lsblk on Linux, Get-Disk/Get-Partition/Get-Volume on Windows).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_attached_images",
        "description": "List image files currently attached as devices (loop devices via losetup on Linux, mounted ISO/VHD images on Windows).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "inspect_filesystem",
        "description": "Detect the filesystem format (iso9660, ext4, vfat, ntfs, ...) of an image file or device.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Image file, /dev path (Linux) or diskNpM (Windows)"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mount",
        "description": (
            "Mount an image file (ISO/IMG/VHD) or a partition, read-only by default. On Linux image files are "
            "attached to a loop device and mounted with the mount() syscall under /mnt/agent/<name>; on Windows "
            "Mount-DiskImage attaches them and they get a drive letter."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Image path, /dev/sdb1 (Linux) or disk1p2 (Windows)"},
                "mount_point": {"type": "string", "description": "Optional; Linux only, a directory under /mnt or /media"},
                "read_only": {"type": "boolean", "description": "Mount read-only (default true)"},
                "partition": {"type": "integer", "description": "1-based partition number inside a disk image or disk"},
            },
            "required": ["source"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unmount",
        "description": "Unmount a filesystem and release its loop device / disk image. Accepts a mount point, drive letter, image path, device, or the name of something mounted this session.",
        "input_schema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_files",
        "description": "List the files inside a directory, typically a mount point or drive letter, so the user can see what is inside an image.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer", "description": "Max entries to return (default 50)"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]

TOOL_NAMES = {spec["name"] for spec in TOOL_SPECS}
_SPECS = {spec["name"]: spec for spec in TOOL_SPECS}
_JSON_TYPES = {"string": str, "boolean": bool, "integer": int}


def validate_args(name: str, args: Any) -> Dict[str, Any]:
    """
    Check an LLM-generated tool call against the tool's JSON schema before anything runs.
    The error text is written for the model, so it can correct the call and try again.
    """
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolError(f"arguments for {name} must be a JSON object, got {type(args).__name__}")
    schema = _SPECS[name]["input_schema"]
    props = schema["properties"]
    for key in schema.get("required", []):
        if key not in args:
            raise ToolError(f"missing required argument '{key}' for {name}")
    for key, value in args.items():
        if key not in props:
            expected = ", ".join(props) or "no arguments"
            raise ToolError(f"unknown argument '{key}' for {name} (expected: {expected})")
        want = props[key]["type"]
        if not isinstance(value, _JSON_TYPES[want]) or (want == "integer" and isinstance(value, bool)):
            article = "an" if want[0] in "aeiou" else "a"
            raise ToolError(f"argument '{key}' for {name} must be {article} {want}, "
                            f"got {type(value).__name__} {value!r}")
    return args


class ToolBox:
    def __init__(self, platform: Platform, session: Session):
        self.platform = platform
        self.session = session

    @property
    def runner(self):
        return self.platform.r

    def call(self, name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        handler = getattr(self, f"_tool_{name}", None) if name in TOOL_NAMES else None
        if handler is None:
            return {"ok": False, "error": f"unknown tool '{name}'"}
        try:
            return {"ok": True, **handler(**validate_args(name, args))}
        except TypeError as e:
            return {"ok": False, "error": f"bad arguments for {name}: {e}"}
        except (ToolError, OSError) as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------ tools

    def _tool_list_block_devices(self):
        return {"devices": self.platform.list_block_devices()}

    def _tool_list_attached_images(self):
        return {"images": self.platform.list_attached_images()}

    def _tool_inspect_filesystem(self, path: str):
        path = self._resolve_source(path)
        return {"path": path, "filesystem": self.platform.detect_filesystem(path)}

    def _tool_mount(self, source: str, mount_point: Optional[str] = None,
                    read_only: bool = True, partition: Optional[int] = None):
        src = self._resolve_source(source)
        record, method = self.platform.mount(src, read_only, mount_point, partition, self.session.mount_points())
        self.session.add(record)
        return {**record.to_dict(), "method": method}

    def _tool_unmount(self, target: str):
        record = self.session.find(target)
        if record is None and target.strip().lower() in ("it", "that", "this", "last"):
            raise ToolError("nothing has been mounted in this session yet; give a drive letter (D:) or an image path")
        if record is None:
            # A relative image path ("samples/test.iso"): match it against the full path stored at mount time,
            # and hand the OS the full path, since Dismount-DiskImage cannot resolve relative ones
            path = Path(target.strip().strip("'\"")).expanduser()
            if path.is_file():
                target = str(path.resolve())
                record = self.session.find(target)
        result = self.platform.unmount(target, record)
        if record:
            self.session.remove(record)
        return result

    def _tool_list_files(self, path: str, limit: int = 50):
        record = self.session.find(path)
        path = record.mount_point if record else path
        return {"path": path, "entries": self.platform.list_dir(path, limit)}

    # ------------------------------------------------------------ helpers

    def _resolve_source(self, source: str) -> str:
        source = source.strip().strip("'\"")
        if self.platform.is_device(source):
            return source
        path = Path(source).expanduser()
        if not self.runner.dry_run:
            if not path.exists():
                raise ToolError(f"'{source}' not found (looked in {Path.cwd()})")
            return str(path.resolve())
        # Dry-run of another OS: keep the path as typed so the trace looks like that OS
        return str(path.resolve()) if self.platform.name == config.HOST_PLATFORM else source
