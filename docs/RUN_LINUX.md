# Run on Linux

Requirements: Ubuntu/Debian/Fedora with Python 3.7+ (`python3 --version`) and `util-linux` (provides `lsblk`, `losetup`, `mount` - installed by default).

1. **Get the code**
   ```bash
   git clone https://github.com/Akshat-git-dev/os_mount_terminal.git
   cd os_mount_terminal
   ```
   (No git? `wget https://github.com/Akshat-git-dev/os_mount_terminal/archive/refs/heads/main.zip && unzip main.zip && cd os_mount_terminal-main`)

2. **Start the terminal** (mounting needs root)
   ```bash
   sudo python3 -m mountagent
   ```

3. **Type requests** (press Enter at each `[Y/n]`):
   ```
   show me all disks and partitions
   mount samples/test.iso so I can look at the files inside
   which loop devices are in use?
   unmount it
   exit
   ```
   The ISO is attached to `/dev/loopN` and mounted read-only at `/mnt/agent/test`.

Notes
- No sudo in the lab? `python3 -m mountagent --dry-run` shows every command and syscall without running it.
- Launcher script: `chmod +x bin/mount-agent && sudo ./bin/mount-agent`
- `losetup: cannot find an unused loop device` -> `sudo modprobe loop`
- Leftover mounts after a crash: `sudo umount /mnt/agent/*` then `sudo losetup -D`
- Run the tests: `python3 -m unittest discover tests` - and the evaluation (live timings need root): `sudo python3 eval/evaluate.py`
