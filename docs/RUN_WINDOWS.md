# Run on Windows

Requirements: Windows 10/11 and Python 3.7+ ([python.org/downloads](https://www.python.org/downloads/), tick "Add python.exe to PATH").

1. **Get the code** - either
   ```powershell
   git clone https://github.com/Akshat-git-dev/os_mount_terminal.git
   cd os_mount_terminal
   ```
   or download the [ZIP](https://github.com/Akshat-git-dev/os_mount_terminal/archive/refs/heads/main.zip), extract it, and `cd` into the extracted folder in PowerShell.

2. **Start the terminal**
   ```powershell
   python -m mountagent
   ```

3. **Type requests** (press Enter at each `[Y/n]`):
   ```
   mount samples/test.iso so I can look at the files inside
   which images are attached?
   unmount it
   exit
   ```
   The ISO appears as a new drive (e.g. `D:\`) - you can also open it in File Explorer.

Notes
- ISO files mount from a normal terminal. VHD/VHDX files and real partitions (`mount partition 1 of disk 1`) need **Run as administrator**.
- Try it without mounting anything: `python -m mountagent --dry-run`
- See the Linux commands on Windows (simulated): `python -m mountagent --platform linux`
- Run the tests: `python -m unittest discover tests` - and the evaluation: `python eval/evaluate.py`
