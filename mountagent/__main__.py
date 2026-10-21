"""
Entry point:  python -m mountagent [options] ["one-shot request"]

  sudo python3 -m mountagent                      Linux, interactive (live)
  python -m mountagent                            Windows, interactive (live)
  python -m mountagent --dry-run                  either OS, simulated
  python -m mountagent --platform linux           simulate Linux on a Windows PC (and vice versa)
  python -m mountagent "mount ubuntu.iso"         run one request and exit
"""

import argparse
import sys

from . import __version__, config
from .agent.backends import create_backend
from .core.platforms import get_platform
from .core.runner import Runner
from .core.session import Session
from .terminal import render
from .terminal.shell import Shell


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mount-agent",
                                 description="Natural-language terminal for mounting disk images and partitions "
                                             "on Linux and Windows.")
    ap.add_argument("request", nargs="*", help="run a single request and exit")
    ap.add_argument("-b", "--backend", choices=["auto", "claude", "ollama", "offline"], default="auto",
                    help="what interprets your sentences (default: auto)")
    ap.add_argument("-p", "--platform", choices=["auto", "linux", "windows"], default="auto",
                    help="which OS's tools to use (default: this machine's)")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="print the commands/syscalls without running them")
    ap.add_argument("-y", "--yes", action="store_true", help="don't ask before mount/unmount")
    ap.add_argument("--no-trace", action="store_true", help="hide the commands that were run")
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    platform_name = (config.HOST_PLATFORM or "linux") if args.platform == "auto" else args.platform
    dry_run = args.dry_run
    if platform_name != config.HOST_PLATFORM and not dry_run:
        print(render.yellow(f"This machine can't run {platform_name} commands - "
                            "switching to dry-run mode (commands are simulated)."))
        dry_run = True

    session = Session()
    platform = get_platform(platform_name, Runner(dry_run))
    try:
        backend = create_backend(args.backend, session, platform.description)
    except ImportError:
        print(render.red("The Claude backend needs the SDK:  pip install anthropic"))
        return 1

    shell = Shell(backend, platform, session, confirm=not args.yes, show_trace=not args.no_trace)
    if args.request:
        shell.run_once(" ".join(args.request))
    else:
        shell.loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
