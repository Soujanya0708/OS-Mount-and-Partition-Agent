"""
generate_student_diagrams.py
Generates two high-resolution, student-grade engineering diagrams:
1. diagram_block.png: System Architecture Block Diagram
2. diagram_flowchart.png: Detailed Operational Flowchart with HITL and Syscalls
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches

def generate_block_diagram(output_path="diagram_block.png"):
    fig, ax = plt.subplots(figsize=(11, 4.8), dpi=300)
    ax.set_xlim(0, 110)
    ax.set_ylim(0, 52)
    ax.axis('off')
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')

    # Palette
    c_blue = '#1E40AF'
    c_slate = '#334155'
    c_purple = '#6D28D9'
    c_teal = '#0F766E'
    c_green = '#047857'
    c_red = '#B91C1C'
    c_border = '#64748B'

    # Helper function for blocks
    def make_block(x, y, w, h, title, subtitle="", color='#1E40AF', bg='#F8FAFC', lw=1.5):
        # shadow
        ax.add_patch(patches.FancyBboxPatch((x + 0.3, y - 0.3), w, h,
                                           boxstyle="round,pad=0.2,rounding_size=0.8",
                                           fc='#CBD5E1', ec='none', alpha=0.5, zorder=1))
        # main box
        ax.add_patch(patches.FancyBboxPatch((x, y), w, h,
                                           boxstyle="round,pad=0.2,rounding_size=0.8",
                                           fc=bg, ec=color, lw=lw, zorder=2))
        # top bar
        bar_h = 3.6
        ax.add_patch(patches.FancyBboxPatch((x, y + h - bar_h), w, bar_h,
                                           boxstyle="round,pad=0.2,rounding_size=0.6",
                                           fc=color, ec='none', zorder=3))
        # title
        ax.text(x + w/2, y + h - bar_h/2, title, ha='center', va='center',
                fontsize=8, fontweight='bold', color='#FFFFFF', zorder=4, family='sans-serif')
        # subtitle
        if subtitle:
            ax.text(x + w/2, y + (h - bar_h)/2, subtitle, ha='center', va='center',
                    fontsize=7, color='#1E293B', zorder=4, family='sans-serif', multialignment='center', linespacing=1.15)

    def make_arrow(x1, y1, x2, y2, label="", color='#475569', rad=0.0):
        cstyle = f"arc3,rad={rad}" if rad != 0 else "arc3,rad=0"
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4,
                                    mutation_scale=9, shrinkA=2, shrinkB=2,
                                    connectionstyle=cstyle), zorder=5)
        if label:
            mx, my = (x1 + x2)/2, (y1 + y2)/2 + (1.2 if rad >= 0 else -1.2)
            ax.text(mx, my, label, ha='center', va='center',
                    fontsize=6.5, fontweight='bold', color=color, zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", fc="#FFFFFF", ec="#CBD5E1", lw=0.5, alpha=0.95))

    # Outer containers (Subsystems)
    # Container 1: Client Space (Unprivileged User)
    ax.add_patch(patches.FancyBboxPatch((2, 2), 24, 48, boxstyle="round,pad=0.4,rounding_size=1.2",
                                       fc='#F8FAFC', ec='#94A3B8', lw=1.2, ls='--', zorder=0))
    ax.text(14, 48, "USER SPACE (Unprivileged)", ha='center', va='center',
            fontsize=8, fontweight='bold', color='#475569')

    # Container 2: Agent Daemon (Privileged Service)
    ax.add_patch(patches.FancyBboxPatch((32, 2), 48, 48, boxstyle="round,pad=0.4,rounding_size=1.2",
                                       fc='#F1F5F9', ec='#3B82F6', lw=1.2, ls='--', zorder=0))
    ax.text(56, 48, "SYSTEM DAEMON SPACE (Root / CAP_SYS_ADMIN)", ha='center', va='center',
            fontsize=8, fontweight='bold', color='#1E40AF')

    # Container 3: Linux Kernel Subsystem
    ax.add_patch(patches.FancyBboxPatch((85, 2), 23, 48, boxstyle="round,pad=0.4,rounding_size=1.2",
                                       fc='#F0FDF4', ec='#10B981', lw=1.2, ls='--', zorder=0))
    ax.text(96.5, 48, "LINUX KERNEL SPACE", ha='center', va='center',
            fontsize=8, fontweight='bold', color='#047857')

    # Blocks inside User Space
    make_block(4, 30, 20, 14, "Terminal / REPL", "mount_cli.py\nCaptures NL queries\nHistory & ANSI UX", c_blue)
    make_block(4, 8, 20, 16, "IPC Client Stub", "socket.AF_UNIX\nConnects to socket\nJSON Payload Serialization", c_slate)

    # Blocks inside Daemon Space
    make_block(35, 30, 20, 14, "Socket Listener", "service_daemon.py\n/run/mount_agent.sock\nchmod 0o666 perms", c_slate)
    make_block(58, 30, 20, 14, "Intent Router & LLM", "mount_agent.py\nOllama / Llama-3 API\n+ Heuristic Fallback", c_purple)
    make_block(35, 8, 20, 16, "Guardrail Engine", "Regex Blacklist (rm -rf)\nHITL [y/N] Validation\nMount Target Sandbox", c_red)
    make_block(58, 8, 20, 16, "MCP Tool Registry", "mount_tools.py\n• mount_target()\n• list_devices()\n• detect_filesystem()", c_teal)

    # Blocks inside Kernel Space
    make_block(87, 32, 19, 12, "VFS & Syscalls", "libc mount()\nlibc umount2()\nFlags: MS_RDONLY", c_green)
    make_block(87, 18, 19, 11, "Loop Subsystem", "/dev/loopX\nlosetup --partscan\nioctl LOOP_CTL", c_green)
    make_block(87, 5, 19, 10, "Block Devices", "lsblk -J, blkid\n/proc/mounts\n/sys/class/block", c_green)

    # Arrows between blocks
    make_arrow(14, 30, 14, 24, "Raw Input", c_blue)
    make_arrow(24, 16, 35, 37, "Unix Domain Socket", c_slate, rad=-0.12)
    make_arrow(45, 30, 45, 24, "Request", c_slate)
    make_arrow(45, 37, 58, 37, "NL Query", c_purple)
    make_arrow(68, 30, 68, 24, "JSON Tool Spec", c_purple)
    make_arrow(55, 16, 58, 16, "Passed", c_red)
    make_arrow(78, 18, 87, 37, "mount()", c_green)
    make_arrow(78, 14, 87, 23, "losetup", c_green)
    make_arrow(78, 10, 87, 10, "lsblk", c_green)
    make_arrow(35, 12, 14, 12, "Response JSON", '#D97706', rad=0.1)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', pad_inches=0.08)
    plt.close()
    print("Block diagram created at:", output_path)


def generate_flowchart_diagram(output_path="diagram_flowchart.png"):
    fig, ax = plt.subplots(figsize=(10.5, 4.4), dpi=300)
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 48)
    ax.axis('off')
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')

    def draw_node(x, y, w, h, text, shape="rect", color="#1E40AF", bg="#F8FAFC"):
        if shape == "rect":
            ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.6",
                                               fc=bg, ec=color, lw=1.4, zorder=2))
            ax.text(x + w/2, y + h/2, text, ha='center', va='center',
                    fontsize=6.8, fontweight='bold', color=color, zorder=3, family='sans-serif', multialignment='center')
        elif shape == "diamond":
            pts = [[x + w/2, y], [x + w, y + h/2], [x + w/2, y + h], [x, y + h/2]]
            ax.add_patch(patches.Polygon(pts, closed=True, fc='#FEF3C7', ec='#D97706', lw=1.4, zorder=2))
            ax.text(x + w/2, y + h/2, text, ha='center', va='center',
                    fontsize=6.5, fontweight='bold', color='#B45309', zorder=3, family='sans-serif', multialignment='center')
        elif shape == "pill":
            ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=2.0",
                                               fc='#EEF2FF', ec='#4338CA', lw=1.4, zorder=2))
            ax.text(x + w/2, y + h/2, text, ha='center', va='center',
                    fontsize=7, fontweight='bold', color='#4338CA', zorder=3, family='sans-serif')

    def draw_conn(x1, y1, x2, y2, label="", color="#475569", rad=0.0):
        cstyle = f"arc3,rad={rad}" if rad != 0 else "arc3,rad=0"
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1.3,
                                    mutation_scale=8, shrinkA=2, shrinkB=2,
                                    connectionstyle=cstyle), zorder=4)
        if label:
            mx, my = (x1 + x2)/2, (y1 + y2)/2 + (1.0 if rad >= 0 else -1.0)
            ax.text(mx, my, label, ha='center', va='center',
                    fontsize=6.2, fontweight='bold', color=color, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.1", fc="#FFFFFF", ec="#E2E8F0", lw=0.5))

    # Flow Steps
    # Top Row: Initiation to Guardrail
    draw_node(2, 36, 12, 8, "Start / User\nNL Prompt", "pill")
    draw_node(18, 36, 15, 8, "mount_cli.py\nIPC Socket Send", "rect", "#1E40AF", "#EFF6FF")
    draw_node(37, 36, 16, 8, "service_daemon\nDaemon Worker", "rect", "#334155", "#F1F5F9")
    draw_node(57, 36, 17, 8, "Intent Parser\nOllama / Fallback", "rect", "#6D28D9", "#F5F3FF")
    draw_node(78, 35, 14, 10, "Destructive\nCommand?", "diamond")
    draw_node(96, 36, 8, 8, "Abort &\nLog", "pill")

    # Connectors Top Row
    draw_conn(14, 40, 18, 40)
    draw_conn(33, 40, 37, 40, "JSON")
    draw_conn(53, 40, 57, 40, "Query")
    draw_conn(74, 40, 78, 40, "Tool JSON")
    draw_conn(92, 40, 96, 40, "Yes (rm -rf)", "#DC2626")

    # Mid Row: HITL Gate & Device Logic
    draw_node(77, 19, 16, 10, "High Risk\nOperation?", "diamond")
    draw_node(96, 19, 8, 8, "HITL [y/N]\nPrompt", "rect", "#D97706", "#FFFBEB")
    draw_node(57, 20, 16, 8, "Is Disk Image?\n(.iso / .img)", "diamond")
    draw_node(37, 20, 16, 8, "losetup --partscan\nMap /dev/loopX", "rect", "#0F766E", "#F0FDFA")
    draw_node(18, 20, 15, 8, "Format Detector\nblkid / file utility", "rect", "#0F766E", "#F0FDFA")

    # Connectors Mid Row
    draw_conn(85, 35, 85, 29, "No (Safe)", "#059669")
    draw_conn(93, 24, 96, 24, "Yes")
    draw_conn(100, 19, 85, 9, "Confirmed", "#059669", rad=-0.2)
    draw_conn(77, 24, 73, 24, "No / Auto", "#059669")
    draw_conn(57, 24, 53, 24, "Yes (ISO)")
    draw_conn(65, 20, 25, 12, "No (Block Dev)", "#334155", rad=0.2)
    draw_conn(37, 24, 33, 24)

    # Bottom Row: Execution & Feedback
    draw_node(4, 5, 18, 8, "Create Safe Mount\n/mnt/agent/<name>", "rect", "#047857", "#ECFDF5")
    draw_node(26, 5, 22, 8, "libc mount() Syscall\nMS_RDONLY | MS_NOSUID", "rect", "#047857", "#ECFDF5")
    draw_node(52, 5, 20, 8, "Verify Mount Point\nUpdate /proc/mounts", "rect", "#047857", "#ECFDF5")
    draw_node(76, 5, 16, 8, "Format Telemetry\nJSON Response", "rect", "#334155", "#F1F5F9")
    draw_node(95, 5, 9, 8, "Terminal\nOutput", "pill")

    # Connectors Bottom Row
    draw_conn(18, 20, 13, 13)
    draw_conn(22, 9, 26, 9)
    draw_conn(48, 9, 52, 9)
    draw_conn(72, 9, 76, 9)
    draw_conn(92, 9, 95, 9, "Socket")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', pad_inches=0.08)
    plt.close()
    print("Flowchart diagram created at:", output_path)

if __name__ == "__main__":
    generate_block_diagram()
    generate_flowchart_diagram()
