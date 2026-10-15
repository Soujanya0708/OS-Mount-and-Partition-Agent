#!/usr/bin/env bash
# demo.sh — Demonstration walkthrough of the Mount & Partition Agent
#
# This script shows example prompts you can type at the agent's REPL.
# It does NOT run the agent itself (you need root for that).
#
# Usage:
#   bash demo.sh          -- prints the demo script
#   sudo -E python3 mount_agent.py   -- then type the prompts below

set -e

BOLD="\033[1m"
CYAN="\033[1;36m"
GREEN="\033[1;32m"
RESET="\033[0m"

echo -e "${BOLD}================================================${RESET}"
echo -e "${BOLD}  Mount & Partition Agent — Demo Walkthrough   ${RESET}"
echo -e "${BOLD}================================================${RESET}"
echo ""
echo -e "Start the agent:  ${CYAN}sudo -E python3 mount_agent.py${RESET}"
echo ""
echo -e "${BOLD}── Step 1: Mount an ISO ─────────────────────────${RESET}"
echo -e "${GREEN}>${RESET} Mount ~/Downloads/ubuntu-22.04.iso so I can explore the files"
echo ""
echo "   The agent will:"
echo "   1. attach_loop  → attaches the ISO to /dev/loop0"
echo "   2. detect_filesystem → identifies iso9660"
echo "   3. mount_device → mounts at /mnt/agent/ubuntu-22.04-iso"
echo "   4. list_files   → shows you the top-level contents"
echo ""
echo -e "${BOLD}── Step 2: Check what's mounted ─────────────────${RESET}"
echo -e "${GREEN}>${RESET} What's mounted right now?"
echo ""
echo -e "${BOLD}── Step 3: Browse a subfolder ───────────────────${RESET}"
echo -e "${GREEN}>${RESET} List the files inside the casper folder"
echo ""
echo -e "${BOLD}── Step 4: Inspect a disk image with partitions ─${RESET}"
echo -e "${GREEN}>${RESET} Attach debian.img and show me its partitions"
echo ""
echo "   The agent will:"
echo "   1. attach_loop  → attaches debian.img to /dev/loop1"
echo "   2. list_block_devices → shows loop1p1, loop1p2 ..."
echo "   3. detect_filesystem on each partition"
echo "   4. Ask you which partition to mount"
echo ""
echo -e "${BOLD}── Step 5: Clean up ─────────────────────────────${RESET}"
echo -e "${GREEN}>${RESET} Unmount everything and detach all loop devices"
echo ""
echo -e "${BOLD}── Step 6: Exit ─────────────────────────────────${RESET}"
echo "   Press Ctrl-D or Ctrl-C"
echo ""
echo -e "${BOLD}================================================${RESET}"
echo -e " Tip: pass ${CYAN}--allow-real-disks${RESET} to also mount /dev/sdX"
echo -e "${BOLD}================================================${RESET}"
