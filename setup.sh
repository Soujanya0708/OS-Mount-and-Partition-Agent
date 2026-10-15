#!/usr/bin/env bash
# setup.sh — One-shot setup for the Mount & Partition Agent
# Run once after cloning: bash setup.sh

set -e

echo "============================================="
echo " Mount & Partition Agent — Environment Setup"
echo "============================================="

# ── 1. Check Python version ────────────────────────────────────────────────
PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
    echo "ERROR: python3 not found. Install Python 3.10+ first."
    exit 1
fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[1/4] Found Python $PY_VER"

PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10 or newer required (found $PY_VER)."
    exit 1
fi

# ── 2. Install Python dependencies ────────────────────────────────────────
echo "[2/4] Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install -r requirements.txt
echo "      Done."

# ── 3. Check system tools ─────────────────────────────────────────────────
echo "[3/4] Checking system tools..."
MISSING=()
for tool in lsblk losetup blkid udevadm; do
    if ! command -v "$tool" &>/dev/null; then
        MISSING+=("$tool")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "WARNING: Missing system tools: ${MISSING[*]}"
    echo "         Install with: sudo apt install util-linux  (Debian/Ubuntu)"
    echo "         Or:           sudo dnf install util-linux  (Fedora/RHEL)"
else
    echo "      All system tools found."
fi

# ── 4. Check GEMINI_API_KEY ───────────────────────────────────────────────
echo "[4/4] Checking GEMINI_API_KEY..."
if [ -z "$GEMINI_API_KEY" ]; then
    echo ""
    echo "  GEMINI_API_KEY is not set."
    echo "  Get a free key at: https://aistudio.google.com/app/apikey"
    echo ""
    echo "  Then run:"
    echo "    export GEMINI_API_KEY=\"your-key-here\""
    echo "    sudo -E python3 mount_agent.py"
else
    echo "      GEMINI_API_KEY is set. ✓"
    echo ""
    echo "Setup complete! Run the agent with:"
    echo "  sudo -E python3 mount_agent.py"
fi
