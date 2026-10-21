"""
runner.py - Single choke point for every external command the agent runs.
Records a trace of commands/syscalls so the terminal can show exactly what happened,
and switches to the simulator in dry-run mode.
"""

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List

from .simulator import Simulator


class ToolError(Exception):
    """A system tool failed; the message is safe to show to the user."""


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str


def ps_quote(value: str) -> str:
    """Quote a string as a PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"


class Runner:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.sim = Simulator()
        self.trace: List[str] = []

    def run(self, cmd: List[str], check: bool = True) -> Result:
        self.trace.append(" ".join(shlex.quote(c) for c in cmd))
        if self.dry_run:
            return Result(0, self.sim.respond(cmd), "")

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise ToolError(f"'{cmd[0]}' is not installed on this system")

        if check and proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
            raise ToolError(f"{cmd[0]} failed: {detail}")
        return Result(proc.returncode, proc.stdout, proc.stderr)

    def powershell(self, script: str, display: str, sim_key: str, **sim_args) -> Any:
        """
        Run a PowerShell script that prints JSON (or nothing) and return the parsed value.
        `display` is the short form shown in the trace; `sim_key` selects the dry-run answer.
        """
        self.trace.append(f"PS> {display}")
        if self.dry_run:
            out = self.sim.powershell(sim_key, **sim_args)
        else:
            wrapped = ("$ErrorActionPreference = 'Stop'; "
                       "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                       f"try {{ {script} }} catch {{ [Console]::Error.WriteLine($_.Exception.Message); exit 1 }}")
            try:
                proc = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", wrapped],
                                      capture_output=True, text=True, encoding="utf-8")
            except FileNotFoundError:
                raise ToolError("PowerShell was not found")
            if proc.returncode != 0:
                raise ToolError(proc.stderr.strip().splitlines()[0] if proc.stderr.strip()
                                else f"PowerShell exited with code {proc.returncode}")
            out = proc.stdout

        out = (out or "").strip()
        if not out:
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            raise ToolError(f"unexpected PowerShell output: {out[:200]}")

    def note(self, line: str):
        """Record an action that is not a subprocess (e.g. a direct syscall)."""
        self.trace.append(line)

    def take_trace(self) -> List[str]:
        trace, self.trace = self.trace, []
        return trace


def as_list(value: Any) -> List[Dict[str, Any]]:
    """ConvertTo-Json turns one-element arrays into a bare object; undo that."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]
