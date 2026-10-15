# 🗂️ Mount & Partition Agent

A **natural-language Linux storage assistant** powered by **Google Gemini**.  
Type plain English — the agent translates your intent into `lsblk`, `losetup`, and `mount(2)` syscalls, so you can explore disk images and ISO files without memorising any commands.

```
> Mount ~/Downloads/ubuntu.iso so I can look at the files inside
  [tool] attach_loop({"image_path": "/home/user/Downloads/ubuntu.iso"})
  [tool] detect_filesystem({"device": "/dev/loop0"})
  [tool] mount_device({"device": "/dev/loop0", "name": "ubuntu-iso"})
  [tool] list_files({"name": "ubuntu-iso"})

Mounted at /mnt/agent/ubuntu-iso (iso9660, read-only).
Contents: casper/  dists/  EFI/  isolinux/  ...
```

---

## ✨ Features

| Feature | Detail |
|---|---|
| **Natural-language interface** | Describe what you want in plain English |
| **ISO & disk image support** | `.iso`, `.img`, `.raw`, `.qcow2` (raw loop) |
| **Auto filesystem detection** | Uses `blkid` — iso9660, ext4, vfat, btrfs … |
| **Partition-aware** | Calls `losetup --partscan`; can mount individual partitions |
| **Read-only by default** | Asks for terminal confirmation before any write mount |
| **Safe file browsing** | `list_files` is chroot-like; symlinks cannot escape the mountpoint |
| **Auto cleanup** | Detaches loop devices on unmount / failure |
| **Real-disk guard** | `/dev/sdX` / NVMe blocked unless `--allow-real-disks` is passed |

---

## 📋 Requirements

- **OS**: Linux (uses `losetup`, `mount(2)`, `/proc/self/mountinfo`)
- **Root**: `sudo -E` (mount syscalls require root)
- **Python**: 3.10 or newer
- **Packages**: see [`requirements.txt`](requirements.txt)

---

## 🚀 Quick Start

### 1 — Clone the repo

```bash
git clone https://github.com/<your-username>/mount-partition-agent.git
cd mount-partition-agent
```

### 2 — Install dependencies

```bash
pip install -r requirements.txt
# or, using the setup script:
bash setup.sh
```

### 3 — Set your Gemini API key

Get a free key at <https://aistudio.google.com/app/apikey>.

```bash
export GEMINI_API_KEY="your-key-here"
```

### 4 — Run as root (required for mount)

```bash
sudo -E python3 mount_agent.py
```

> **`sudo -E`** preserves your `GEMINI_API_KEY` environment variable.

---

## 💬 Example Prompts

```
> Mount ~/Downloads/ubuntu-22.04.iso so I can explore it
> What block devices are currently attached?
> What's mounted right now?
> List the files inside the ubuntu-iso mount
> Show me what's inside the casper/ folder
> Unmount ubuntu-iso and clean up the loop device
> Attach debian.img read-only and show me its partitions
> Detach /dev/loop3
```

---

## 🛠️ Exposed Tools (Gemini Function Declarations)

| Tool | Underlying command | What it does |
|---|---|---|
| `list_block_devices` | `lsblk -J` | All block devices, partitions, filesystem types, mountpoints |
| `list_loop_devices` | `losetup -J -l` | Active loop devices and their backing files |
| `attach_loop` | `losetup --find --show --partscan` | Attach an image file to a new loop device |
| `detect_filesystem` | `blkid -p -o export` | Probe a device for its filesystem type / UUID / label |
| `mount_device` | `mount(2)` syscall via `ctypes` | Mount a device at `/mnt/agent/<name>` |
| `list_mounts` | `/proc/self/mountinfo` | Mounts this agent has created |
| `unmount` | `umount2(2)` syscall + `losetup -d` | Unmount and optionally detach the loop device |
| `detach_loop_device` | `losetup -d` | Detach a stale loop device |
| `list_files` | `pathlib.Path.iterdir()` | Browse a directory inside a mount (confined to mountpoint) |

---

## 🔒 Safety Model

The LLM **never gets a shell**. Every operation goes through a curated Python function:

1. **No `shell=True`** — all subprocess calls use fixed `argv` lists.
2. **Mount root confinement** — mounts only land under `/mnt/agent/`.
3. **Read-only by default** — read-write requires explicit `y` at the terminal.
4. **Loop-device only** — real disks (`/dev/sdX`) are blocked unless `--allow-real-disks`.
5. **Symlink-safe browsing** — `list_files` resolves symlinks and rejects paths outside the mountpoint.
6. **Cleanup on failure** — the agent detaches loop devices it created if mounting fails.

---

## ⚙️ CLI Options

```
sudo -E python3 mount_agent.py [--allow-real-disks]

Options:
  --allow-real-disks   Permit mounting non-loop block devices
                       (/dev/sdX, /dev/nvme0n1p2, etc.)
```

---

## 📁 Project Structure

```
mount-partition-agent/
├── mount_agent.py      # Main agent — Gemini function-calling loop
├── requirements.txt    # Python dependencies
├── setup.sh            # One-shot environment setup script
├── demo.sh             # Demo walkthrough script (dry-run prompts)
├── .gitignore          # Git ignore rules
├── README.md           # This file
└── note.txt            # Developer notes — all files & functionalities
```

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss changes.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
