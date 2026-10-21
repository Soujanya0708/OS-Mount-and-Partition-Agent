import matplotlib.pyplot as plt
import matplotlib.patches as patches

def create_architecture_diagram(output_path="arch_diagram.png"):
    fig, ax = plt.subplots(figsize=(10.5, 3.4), dpi=300)
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 36)
    ax.axis('off')

    # Background canvas
    fig.patch.set_facecolor('#FFFFFF')
    ax.set_facecolor('#FFFFFF')

    # Color palette (modern, professional tech aesthetic)
    c_user = '#1E293B'       # Dark Slate
    c_repl = '#2563EB'       # Blue
    c_llm = '#7C3AED'        # Purple
    c_guard = '#DC2626'      # Red
    c_mcp = '#0D9488'        # Teal
    c_sys = '#059669'        # Emerald

    def draw_box(x, y, w, h, step_num, title, subtitle, color):
        # Soft shadow
        shadow = patches.FancyBboxPatch((x + 0.35, y - 0.35), w, h,
                                       boxstyle="round,pad=0.3,rounding_size=1.0",
                                       facecolor='#CBD5E1', edgecolor='none', alpha=0.45, zorder=1)
        ax.add_patch(shadow)
        # Main box container
        box = patches.FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.3,rounding_size=1.0",
                                    facecolor='#FFFFFF', edgecolor=color, linewidth=1.6, zorder=2)
        ax.add_patch(box)
        # Top title banner
        banner_h = 3.8
        header = patches.FancyBboxPatch((x, y + h - banner_h), w, banner_h,
                                       boxstyle="round,pad=0.3,rounding_size=0.8",
                                       facecolor=color, edgecolor='none', zorder=3)
        ax.add_patch(header)

        # Title text
        full_title = f"{step_num}. {title}" if step_num else title
        ax.text(x + w/2, y + h - banner_h/2, full_title, ha='center', va='center',
                fontsize=7.8, fontweight='bold', color='#FFFFFF', zorder=4, family='sans-serif')
        # Subtitle / content text
        ax.text(x + w/2, y + (h - banner_h)/2, subtitle, ha='center', va='center',
                fontsize=7.0, color='#334155', zorder=4, family='sans-serif', multialignment='center',
                linespacing=1.2)

    def draw_arrow(x1, y1, x2, y2, label="", color='#64748B', rad=0.0):
        connectionstyle = f"arc3,rad={rad}" if rad != 0 else "arc3,rad=0"
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5,
                                    mutation_scale=10, shrinkA=2, shrinkB=2,
                                    connectionstyle=connectionstyle),
                    zorder=5)
        if label:
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 + (1.2 if rad >= 0 else -1.2)
            ax.text(mid_x, mid_y, label, ha='center', va='center',
                    fontsize=6.5, fontweight='bold', color=color, zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", fc="#FFFFFF", ec="#E2E8F0", lw=0.5, alpha=0.95))

    # Top Row: 5 Forward Steps
    box_w = 17
    box_h = 13.5
    y_top = 19

    # 1. User Input
    draw_box(2, y_top, 16.5, box_h, "1", "USER INPUT", "Natural Language\nPrompt / Terminal", c_user)

    # 2. Interface Layer (REPL)
    draw_box(22.5, y_top, 17.5, box_h, "2", "INTERFACE (REPL)", "Interactive Shell\nHistory & Socket IPC", c_repl)

    # 3. LLM Router
    draw_box(44, y_top, 17.5, box_h, "3", "ORCHESTRATION", "LLM Intent Parser\n& Tool Matcher", c_llm)

    # 4. Guardrails
    draw_box(65.5, y_top, 17.5, box_h, "4", "SECURITY GUARD", "HITL Policy &\nRegex Sanitizer", c_guard)

    # 5. MCP Server
    draw_box(87, y_top, 16.5, box_h, "5", "MCP SERVER", "Tool Registry\n(Mount, Stats, Net)", c_mcp)

    # Bottom Row: System Execution Layer (Centrally Placed)
    y_bot = 2.5
    draw_box(36, y_bot, 42, 10.5, "6", "SYSTEM EXECUTION LAYER (LINUX KERNEL)", "Privileged Daemon, libc mount(), losetup Loopback, lsblk, Isolated Sandbox", c_sys)

    # Forward Pipeline Arrows (Top Row)
    draw_arrow(18.5, y_top + 6.7, 22.5, y_top + 6.7, "NL Prompt", c_repl)
    draw_arrow(40, y_top + 6.7, 44, y_top + 6.7, "Raw Input", c_llm)
    draw_arrow(61.5, y_top + 6.7, 65.5, y_top + 6.7, "Tool Call", c_guard)
    draw_arrow(83, y_top + 6.7, 87, y_top + 6.7, "Validated", c_mcp)

    # Down to Kernel Execution
    draw_arrow(95, y_top, 78, y_bot + 8.5, "JSON-RPC Exec", c_mcp)

    # Return / Telemetry Feedback Loop (from Kernel to Interface Layer & User)
    draw_arrow(36, y_bot + 5.5, 27, y_top, "Structured Output & Status", '#D97706', rad=0.12)
    draw_arrow(22.5, y_top + 2, 18.5, y_top + 2, "Feedback", c_user)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight', pad_inches=0.08)
    plt.close()
    print("Clean architecture diagram generated successfully at:", output_path)

if __name__ == "__main__":
    create_architecture_diagram()
