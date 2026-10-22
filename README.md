# Mount & Partition Agent (terminal)

A terminal that takes plain-English requests and mounts disk images and partitions.
It runs on **Linux and Windows**, using each OS's own tools:

| Job                        | Linux                                   | Windows                                         |
|----------------------------|-----------------------------------------|-------------------------------------------------|
| List disks & partitions    | `lsblk`                                 | `Get-Disk`, `Get-Partition`, `Get-Volume`       |
| Attach an image file       | `losetup --find --show` -> `/dev/loopN` | `Mount-DiskImage` (ISO, VHD, VHDX)              |
| Mount it                   | `mount(2)` syscall -> `/mnt/agent/<name>` | Windows assigns a drive letter -> `D:\`       |
| Mount a real partition     | `/dev/sdb1`                             | `disk1p2` via `Add-PartitionAccessPath` (admin) |
| Detect filesystem          | `blkid`, then signature bytes           | signature bytes, or `Get-Volume`                |
| Unmount                    | `umount2(2)` + `losetup -d`             | `Dismount-DiskImage` / `Remove-PartitionAccessPath` |

```
mount-agent> Mount this ubuntu.iso file so I can look at the files inside.
  -> mount(source='ubuntu.iso', read_only=True)
     loop device  /dev/loop0
     filesystem   iso9660
     mount point  /mnt/agent/ubuntu
  commands run:
    $ blkid -o value -s TYPE ubuntu.iso
    $ losetup --find --show --partscan --read-only ubuntu.iso
    $ mkdir -p /mnt/agent/ubuntu
    $ mount("/dev/loop0", "/mnt/agent/ubuntu", "iso9660", MS_RDONLY|MS_NOSUID|MS_NODEV, NULL)
  -> list_files(path='/mnt/agent/ubuntu')
       boot/  casper/  dists/  EFI/ ...
agent: Mounted ubuntu.iso at /mnt/agent/ubuntu (iso9660, read-only).
```

## Quick links

| | |
|---|---|
| Run on **Windows** - step by step | [docs/RUN_WINDOWS.md](docs/RUN_WINDOWS.md) |
| Run on **Linux** - step by step | [docs/RUN_LINUX.md](docs/RUN_LINUX.md) |
| **Review 3 report** - testing, evaluation & results (PDF) | [docs/Review_3_Testing_Evaluation_and_Results.pdf](docs/Review_3_Testing_Evaluation_and_Results.pdf) |
| Review 2 report - architecture & implementation (PDF) | [docs/Review_2_System_Architecture_and_Implementation.pdf](docs/Review_2_System_Architecture_and_Implementation.pdf) |
| Review 1 report - introduction & literature review (PDF) | [docs/Review_1_Introduction_and_Literature_Review.pdf](docs/Review_1_Introduction_and_Literature_Review.pdf) |
| Download as ZIP | [main.zip](https://github.com/Akshat-git-dev/os_mount_terminal/archive/refs/heads/main.zip) |

## Running it

Needs Python 3.7+. No packages are required for the offline mode.
Run every command from the repository folder (the one containing `mountagent/`).

**Linux (Ubuntu / Debian / Fedora)**
```bash
sudo python3 -m mountagent
```

**Windows (PowerShell or Command Prompt)**
```powershell
python -m mountagent
```
A normal terminal can mount ISO files. Mounting VHD/VHDX files or real partitions needs
"Run as administrator".

**Anywhere, nothing mounted for real**
```bash
python -m mountagent --dry-run              # this OS, simulated
python -m mountagent --platform linux       # show the Linux commands on a Windows PC
python -m mountagent --platform windows     # show the Windows commands on a Linux PC
```

Other flags: `--backend auto|claude|ollama|offline`, `--yes` (skip confirmation), `--no-trace`,
and a request as an argument runs once and exits: `python -m mountagent "show partitions"`.

## Things to try

`samples/test.iso` is a tiny ISO (a `readme.txt` and a `docs/` folder) you can mount straight away:

```
mount samples/test.iso so I can look at the files inside
show me all disks and partitions
mount this ubuntu.iso so I can look at the files inside
what filesystem is backup.img?
which images are attached?            (or: which loop devices are in use?)
unmount ubuntu                        (or: unmount it)

# Linux
mount /dev/sdb1 read-write at /mnt/usb
mount disk.img partition 2
show files in /mnt/agent/ubuntu

# Windows
mount C:\Users\me\Downloads\backup.vhdx
mount partition 1 of disk 1
show files in D:
unmount D:
```

Built-ins: `help`, `mounts`, `dryrun on|off`, `trace on|off`, `confirm on|off`, `reset`, `history`, `clear`, `exit`.

## Choosing the brain

| Backend   | Needs                                          | Behaviour |
|-----------|------------------------------------------------|-----------|
| `claude`  | `pip install anthropic` + `ANTHROPIC_API_KEY`  | Native tool use, multi-step, remembers the conversation |
| `ollama`  | Ollama running locally (`ollama run llama3`)   | One JSON tool call per request |
| `offline` | nothing                                        | Regex rules; works with no network |

`auto` (default) picks Claude if a key is set, else Ollama if it is running, else offline.
The LLM is told which OS it is driving, so it uses `/dev/sdb1` paths on Linux and `disk1p2` / drive letters on Windows.

## Folder layout

```
os_project/
├── bin/mount-agent            Linux launcher (sudo ./bin/mount-agent)
├── mountagent/
│   ├── __main__.py            flags, picks OS backend + brain, starts the shell
│   ├── config.py              defaults, OS detection, admin check
│   ├── core/                  talks to the OS
│   │   ├── platforms/
│   │   │   ├── base.py        the interface both OS backends implement
│   │   │   ├── linux.py       lsblk, losetup, blkid, mount()/umount2() via ctypes
│   │   │   └── windows.py     Get-Disk/Get-Volume, Mount-DiskImage, partition access paths
│   │   ├── fsdetect.py        filesystem detection from signature bytes (both OSes)
│   │   ├── runner.py          runs every command/PowerShell script, records the trace
│   │   ├── session.py         remembers what this session mounted ("unmount it")
│   │   └── simulator.py       fake outputs for dry-run on either OS
│   ├── agent/                 language -> tool calls
│   │   ├── tools.py           tool schemas + ToolBox
│   │   ├── heuristic.py       offline parser (Linux and Windows phrasing)
│   │   └── backends.py        claude / ollama / offline
│   └── terminal/
│       ├── shell.py           interactive REPL, built-ins, confirmation prompts
│       └── render.py          colors, device tree, file listings
├── tests/test_agent.py        unit tests (both OSes, dry-run)
├── eval/evaluate.py           accuracy / safety / latency / error-recovery evaluation -> eval/results.json
├── samples/test.iso           small ISO to try mounting
├── docs/
│   ├── RUN_WINDOWS.md, RUN_LINUX.md     step-by-step run guides
│   ├── Review_3_Testing_Evaluation_and_Results.docx / .pdf
│   ├── Review_2_System_Architecture_and_Implementation.pdf, architecture_and_flow.md
│   ├── screenshots/           terminal captures used in Review 3, Chapter 7
│   ├── diagrams/              PNG/SVG/HTML diagrams
│   └── scripts/               scripts that generate the screenshots, diagrams and reports
└── requirements.txt
```

The Review 3 report is a Word document ([.docx](docs/Review_3_Testing_Evaluation_and_Results.docx)) exported to
[PDF](docs/Review_3_Testing_Evaluation_and_Results.pdf). To rebuild it from the repository root (needs `pip install pillow`,
`npm install docx` and Microsoft Word for the PDF export):

```bash
python eval/evaluate.py
python docs/scripts/capture_screenshots.py
node docs/scripts/build_review3_docx.js
powershell -ExecutionPolicy Bypass -File docs/scripts/docx_to_pdf.ps1
```

Screenshots you take yourself can be saved as `docs/screenshots/real_*.png`; they are added to Chapter 7 first.
The Review 2 scripts need `pip install reportlab matplotlib` and are run from `docs/diagrams/`
(e.g. `python ../scripts/generate_diagram.py`).

## Safety

- Mounts are read-only unless you ask for write access (ISOs are always read-only).
- Linux: mount and unmount targets must be under `/mnt` or `/media`; also `nosuid,nodev`.
- Windows: the boot/system partition (C:) is never touched.
- Mount and unmount ask `[Y/n]` before running (turn off with `--yes`).
- If a mount fails, the loop device or disk image it attached is released again.
- Windows cannot read ext4: the agent says so instead of attaching the image.

## Tests and evaluation

```bash
python -m unittest discover tests
python eval/evaluate.py
```

Latest results (offline parser): simple intents 92%, chained intents 71%, destructive inputs blocked 100%,
invalid LLM tool calls caught 100% - details in the Review 3 report.
