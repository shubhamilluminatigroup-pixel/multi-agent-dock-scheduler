import asyncio
import math
import os
import shutil
import subprocess
import sys
import wave
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "docs", "screenshots")
VIDEO_BUILD_DIR = os.path.join(BASE_DIR, "data", "video_build")
DOWNLOADS_DIR = r"C:\Users\2427727\Downloads"
STATIC_DIR = os.path.join(BASE_DIR, "static")
ARTIFACT_DIR = r"C:\Users\2427727\.gemini\antigravity\brain\28d738c2-5a3d-47f9-907e-bddbfc7bf8c1"

os.makedirs(VIDEO_BUILD_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

W, H = 1920, 1080


def get_font(size, bold=False):
    candidates = (
        [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    )
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


FONT_BADGE = get_font(20, bold=True)
FONT_TITLE = get_font(42, bold=True)
FONT_SUB = get_font(23, bold=False)
FONT_CARD_HDR = get_font(20, bold=True)
FONT_CARD_TITLE = get_font(27, bold=True)
FONT_CARD_BODY = get_font(21, bold=False)
FONT_CAPTION = get_font(24, bold=True)
FONT_METRIC_VAL = get_font(46, bold=True)
FONT_METRIC_LBL = get_font(20, bold=True)


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_header(draw, step_idx, total_steps, badge_text, title_text, subtitle_text):
    # Top header banner
    draw.rectangle([0, 0, W, 146], fill=(15, 23, 42))
    draw.rectangle([0, 142, W, 148], fill=(37, 99, 235))

    # Progress bar along very top
    prog_w = int((step_idx / total_steps) * W)
    draw.rectangle([0, 0, prog_w, 6], fill=(56, 189, 248))

    # Pill badge
    draw.rounded_rectangle([48, 26, 310, 68], radius=10, fill=(37, 99, 235))
    draw.text((179, 47), badge_text.upper(), font=FONT_BADGE, fill=(255, 255, 255), anchor="mm")

    # Step counter on top right
    draw.rounded_rectangle([W - 230, 26, W - 48, 68], radius=10, fill=(30, 41, 59), outline=(71, 85, 105), width=2)
    draw.text((W - 139, 47), f"SECTION {step_idx:02d} / {total_steps:02d}", font=FONT_BADGE, fill=(147, 197, 253), anchor="mm")

    # Title & Subtitle
    draw.text((334, 24), title_text, font=FONT_TITLE, fill=(255, 255, 255))
    draw.text((334, 86), subtitle_text, font=FONT_SUB, fill=(148, 163, 184))


def draw_subtitle_caption_bar(draw, narration_text):
    # Bottom closed-caption bar
    bar_top = H - 106
    draw.rectangle([0, bar_top, W, H], fill=(15, 23, 42))
    draw.rectangle([0, bar_top, W, bar_top + 4], fill=(37, 99, 235))

    lines = wrap_text(draw, narration_text, FONT_CAPTION, W - 140)
    lines = lines[:2]
    if len(lines) == 1:
        draw.text((W // 2, bar_top + 54), lines[0], font=FONT_CAPTION, fill=(241, 245, 249), anchor="mm")
    elif len(lines) >= 2:
        draw.text((W // 2, bar_top + 36), lines[0], font=FONT_CAPTION, fill=(241, 245, 249), anchor="mm")
        draw.text((W // 2, bar_top + 72), lines[1], font=FONT_CAPTION, fill=(203, 213, 225), anchor="mm")


def draw_info_card(draw, x, y, w, h, badge, title, bullets, accent=(37, 99, 235), bg=(255, 255, 255)):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=bg, outline=(203, 213, 225), width=2)
    draw.rounded_rectangle([x, y, x + w, y + 12], radius=6, fill=accent)

    cy = y + 26
    if badge:
        draw.text((x + 26, cy), badge.upper(), font=FONT_CARD_HDR, fill=accent)
        cy += 30
    title_lines = wrap_text(draw, title, FONT_CARD_TITLE, w - 52)
    for tl in title_lines:
        draw.text((x + 26, cy), tl, font=FONT_CARD_TITLE, fill=(15, 23, 42))
        cy += 34
    cy += 10

    for b in bullets:
        b_lines = wrap_text(draw, b, FONT_CARD_BODY, w - 76)
        for idx, bl in enumerate(b_lines):
            if idx == 0:
                draw.ellipse([x + 28, cy + 9, x + 38, cy + 19], fill=accent)
            draw.text((x + 50, cy), bl, font=FONT_CARD_BODY, fill=(51, 65, 85))
            cy += 29
        cy += 10


def paste_screenshot_card(canvas, draw, img_path, x, y, w, h, highlight_box=None, callout_label=None):
    # Frame shadow & border
    draw.rounded_rectangle([x - 6, y - 6, x + w + 6, y + h + 6], radius=14, fill=(255, 255, 255), outline=(148, 163, 184), width=3)
    if os.path.exists(img_path):
        im = Image.open(img_path).convert("RGB")
        im_resized = im.resize((w, h), Image.Resampling.LANCZOS)
        canvas.paste(im_resized, (x, y))

    if highlight_box:
        hx, hy, hw, hh = highlight_box
        draw.rounded_rectangle(
            [x + hx, y + hy, x + hx + hw, y + hy + hh],
            radius=10,
            outline=(220, 38, 38),
            width=5,
        )
    if callout_label:
        cx, cy_lbl, txt, col = callout_label
        bbox = draw.textbbox((0, 0), txt, font=FONT_BADGE)
        tw = bbox[2] - bbox[0] + 28
        th = 40
        draw.rounded_rectangle([x + cx, y + cy_lbl, x + cx + tw, y + cy_lbl + th], radius=8, fill=col)
        draw.text((x + cx + tw // 2, y + cy_lbl + th // 2), txt, font=FONT_BADGE, fill=(255, 255, 255), anchor="mm")


CHAPTERS = [
    {
        "id": "01_intro",
        "badge": "INTRODUCTION",
        "title": "Autonomous Multi-Agent ETA Dock & Slot Scheduler",
        "subtitle": "AI Control Tower for Real-Time Dock Optimization, Slot & Dock Swaps, 24-Hr Gantt & Carrier Portal",
        "screenshot": "slide_01_control_tower_overview.png",
        "layout": "hero",
        "card_badge": "PRODUCT OVERVIEW",
        "card_title": "Proactive Multi-Agent Yard & Dock Control",
        "bullets": [
            "5 Specialized Autonomous Agents (Truck, Schedule, ETA, Slot, Execution)",
            "Dual SQLite Architecture (truck_db.sqlite & schedule_db.sqlite)",
            "24-Hour Scrollable Gantt Chart with Frozen Left Track Labels",
            "Variable 30 min, 45 min & 60 min Appointment Durations",
            "Overlapping ETA Red Indicator for Live Collision Detection",
            "Standalone Transport Portal (/transport) for Carriers & Drivers",
        ],
        "narration": (
            "Welcome to the Autonomous Multi-Agent ETA Dock and Slot Scheduler. "
            "This AI Control Tower transforms warehouse dock scheduling from reactive manual firefighting "
            "into proactive, autonomous conflict resolution — connecting live fleet telematics, warehouse schedules, and carrier portals."
        ),
        "callout": (24, 18, "LIVE 5-AGENT AI CONTROL TOWER", (37, 99, 235)),
    },
    {
        "id": "02_problem",
        "badge": "THE PROBLEM",
        "title": "Problem Statement: Why Static Dock Schedules Fail",
        "subtitle": "Highway delays, early arrivals, and overlapping ETA windows create costly dock collisions & yard queues",
        "screenshot": "slide_02_gantt_24h_frozen_and_overlaps.png",
        "layout": "problem_cards",
        "narration": (
            "In traditional warehouse operations, static dock schedules break down the moment trucks hit highway traffic, "
            "arrive hours early, or show up unbooked. When a delayed truck's live arrival window overlaps with the next appointment "
            "on the same dock, it triggers severe bay collisions, costly carrier detention fees, and hours of manual phone and spreadsheet rework."
        ),
    },
    {
        "id": "03_solution_arch",
        "badge": "HOW WE SOLVE IT",
        "title": "5-Agent Autonomous Pipeline & 4-Tier Architecture",
        "subtitle": "Sense, Reason, Act, Decide & Learn (SRADL) across Truck DB (TMS), Schedule DB (WMS) & Live Telematics",
        "screenshot": "slide_01_control_tower_overview.png",
        "layout": "architecture",
        "narration": (
            "Here is how we solve it — using five specialized autonomous agents working together in real time. "
            "First, the Truck Data Agent loads fleet manifests and 30, 45, or 60-minute durations. "
            "Second, the Schedule Data Agent reads 24-hour dock availability across Dock A and Dock B. "
            "Third, the ETA Finder Agent detects arrival variances and highlights Overlapping ETA Red Indicators. "
            "Fourth, the Slot Checking Agent computes Pairwise Slot Swaps and Cross-Dock Swaps, while the fifth agent atomically commits approved schedules."
        ),
    },
    {
        "id": "04_demo_gantt",
        "badge": "PRODUCT DEMO • PART 1",
        "title": "24-Hour Scrollable Gantt, Frozen Headers & Red Overlap Alerts",
        "subtitle": "Synchronized 00:00–24:00 timeline with 30m/45m/60m bars, Frozen Track Column & Overlapping ETA Red Indicator",
        "screenshot": "slide_02_gantt_24h_frozen_and_overlaps.png",
        "layout": "split_demo",
        "card_badge": "24-HR GANTT VISUALIZATION",
        "card_title": "Side-by-Side Schedule Comparison",
        "bullets": [
            "24-Hour Scrollable Timeline (00:00–24:00) with :00, :15, :30 & :45 markers and quick-jump buttons.",
            "Frozen Left Track Column keeps '1. Existing Schedule' and '2. Proposed Schedule' pinned while scrolling.",
            "Variable 30m, 45m & 60m bars scale proportionally to exact appointment duration.",
            "Overlapping ETA Red Indicator highlights colliding arrival windows in red on both Dock 1 and Dock 2.",
            "Uniform red diamond ETA pins (TRK-XXX HH:MM) show exact predicted arrival times.",
        ],
        "accent": (220, 38, 38),
        "callout": (220, 145, "FROZEN LEFT COLUMN + RED OVERLAP INDICATOR", (220, 38, 38)),
        "narration": (
            "Let's walk through the live product demo. On the 24-hour scrollable Gantt chart, the left track header stays frozen in place, "
            "so you can effortlessly compare the Existing Schedule on top against the AI-Proposed Schedule below as you scroll across the day. "
            "Each bar scales to 30, 45, or 60 minutes, and any same-dock collision immediately lights up with our Overlapping ETA Red Indicator."
        ),
    },
    {
        "id": "05_demo_slot_swap",
        "badge": "PRODUCT DEMO • PART 2",
        "title": "Scenario 1: Pairwise Slot Swap (SLOT_SWAP) on Same Dock",
        "subtitle": "Early TRK-103 (ETA 08:05) and Delayed TRK-101 (ETA 10:05) automatically swap slots on DOCK-A",
        "screenshot": "slide_03_slot_swap_gantt.png",
        "layout": "split_demo",
        "card_badge": "SCENARIO 1 • PAIRWISE SLOT SWAP",
        "card_title": "Turning Idle Bays into Throughput",
        "bullets": [
            "Initial State on DOCK-A: TRK-101 (60m) is booked at [08:00–09:00] and TRK-103 (30m) is booked at [10:00–10:30].",
            "Live Disruption: TRK-101 is delayed 2 hours to 10:05, while TRK-103 is arriving 2 hours early at 08:05.",
            "Agent 04 Resolution: Detects complementary variance and proposes a mutual Pairwise Slot Swap on DOCK-A.",
            "Result: TRK-103 unloads immediately at [08:00–08:30] and TRK-101 takes [10:00–11:00] with zero dock idle time.",
        ],
        "accent": (124, 58, 237),
        "callout": (240, 290, "PAIRWISE SLOT SWAP: TRK-103 (08:00) <-> TRK-101 (10:00)", (124, 58, 237)),
        "narration": (
            "Now let's look at Scenario 1: a Pairwise Slot Swap on the same dock. Here, Truck 101 is booked at 8:00 AM on Dock A, "
            "but is running two hours late with a 10:05 AM arrival. Meanwhile, Truck 103 is booked at 10:00 AM, but arrives two hours early at 8:05 AM. "
            "Our Slot Checking Agent spots this match and proposes a mutual Slot Swap — letting Truck 103 unload right away at 8:00 AM "
            "while giving the 10:00 AM slot to Truck 101."
        ),
    },
    {
        "id": "06_demo_dock_swap",
        "badge": "PRODUCT DEMO • PART 3",
        "title": "Scenario 2: Cross-Dock Swap (DOCK_SWAP: DOCK-A ↔ DOCK-B)",
        "subtitle": "Delayed DOCK-A trucks automatically re-route to open, cargo-compatible bays on DOCK-B",
        "screenshot": "slide_05_dock_swap_gantt.png",
        "layout": "split_demo",
        "card_badge": "SCENARIO 2 • CROSS-DOCK SWAP",
        "card_title": "Dynamic Cross-Bay Load Balancing",
        "bullets": [
            "Collision 1: TRK-102 (45m, DOCK-A 09:00) is delayed to ETA 11:05, where DOCK-A [11:00] is occupied by TRK-104.",
            "Cross-Dock Move 1: Agent 04 re-routes TRK-102 to open DOCK-B [11:00–11:45] ('Dock Swap').",
            "Collision 2: TRK-104 (45m, DOCK-A 11:00) is delayed to ETA 12:05, colliding in red with TRK-105 on DOCK-A [12:00].",
            "Cross-Dock Move 2: Agent 04 validates Flatbed compatibility and moves TRK-104 to open DOCK-B [12:00–12:45].",
        ],
        "accent": (217, 119, 6),
        "callout": (240, 460, "CROSS-DOCK SWAP: DOCK-A -> OPEN DOCK-B BAYS", (217, 119, 6)),
        "narration": (
            "In Scenario 2, Cross-Dock Swap, Truck 102 and Truck 104 are both delayed on Dock A into hours that are already occupied by other shipments. "
            "Instead of forcing those drivers to wait in the yard, Agent 4 verifies cargo and equipment compatibility across the warehouse "
            "and dynamically re-routes both trucks from congested Dock A onto open 45-minute bays on Dock B."
        ),
    },
    {
        "id": "07_demo_modal_and_table",
        "badge": "PRODUCT DEMO • PART 4",
        "title": "Interactive What-If ETA Override & Fleet Operations Table",
        "subtitle": "Click any Gantt bar to simulate custom 24-hour ETAs and inspect full fleet telemetry & dispatch logs",
        "screenshot": "slide_07_eta_modal_override.png",
        "layout": "split_demo",
        "card_badge": "WHAT-IF SIMULATION & AUDIT",
        "card_title": "Real-Time Override & Transparency",
        "bullets": [
            "Click-to-Edit Gantt Bars: Clicking any truck bar opens the 24-hour ETA Override Modal.",
            "Instant Recalculation: Saving a new ETA immediately triggers Agents 01–04 to recompute overlaps and swaps.",
            "Granular In-Bar Approval: Each proposed bar features clean '✓ Approve' and '✕' buttons that never cover the truck ID.",
            "Fleet & Audit Tab: Full tabular view of cargo, weights, live arrival windows, pending proposals & dispatch logs.",
        ],
        "accent": (37, 99, 235),
        "callout": (360, 190, "INTERACTIVE 24-HR ETA SIMULATION MODAL", (37, 99, 235)),
        "narration": (
            "Want to run a live what-if simulation? Just click any truck bar on the Gantt chart to open the 24-hour ETA override modal, "
            "enter a new arrival time, and watch the agents recompute optimal slots in milliseconds. "
            "Each proposed bar also includes clean Approve and Reject buttons right next to the truck label."
        ),
    },
    {
        "id": "08_demo_connectors",
        "badge": "PRODUCT DEMO • PART 5",
        "title": "Pluggable DB & Enterprise System Connectors (TMS / WMS / GPS)",
        "subtitle": "Live connection links binding Agent 01, Agent 02 & Agent 03 to SQLite, REST APIs, SQL URIs or Webhooks",
        "screenshot": "slide_09_db_and_external_connections.png",
        "layout": "split_demo",
        "card_badge": "ENTERPRISE INTEGRATION HUB",
        "card_title": "Connect Any TMS, WMS or Telematics Feed",
        "bullets": [
            "1. Truck DB / TMS Link (Agent 01): Local SQLite, External TMS SQLite, REST API, or PostgreSQL URI.",
            "2. Schedule DB / WMS Link (Agent 02): Local Schedule SQLite, External WMS SQLite, REST API, or SQL URI.",
            "3. Live ETA / Telematics Feed (Agent 03): Live Telematics REST API, Samsara Webhook, or Truck DB.",
            "Built-in Diagnostics: 'Test Link', 'Save & Bind to Agent', and 'Sync Agent via Link' with live latency metrics.",
        ],
        "accent": (8, 145, 178),
        "callout": (160, 155, "3 PLUGGABLE AGENT DATA CONNECTORS", (8, 145, 178)),
        "narration": (
            "To plug right into your enterprise stack, the Database and System Connections panel lets you connect "
            "Agent 1 to your Fleet TMS, Agent 2 to your Warehouse WMS, and Agent 3 to live GPS telematics feeds "
            "using SQLite, REST APIs, database URIs, or webhooks — complete with one-click link testing and instant agent sync."
        ),
    },
    {
        "id": "09_demo_transport_portal",
        "badge": "PRODUCT DEMO • PART 6",
        "title": "Standalone Carrier & Driver Transport Portal (/transport)",
        "subtitle": "Role-separated external portal for 1. Manual ETA Input & 2. Booking New 30/45/60m Truck Appointments",
        "screenshot": "slide_10_transport_portal.png",
        "layout": "split_demo",
        "card_badge": "EXTERNAL CARRIER PORTAL",
        "card_title": "Strict Role Separation (/transport)",
        "bullets": [
            "Completely isolated from the internal Control Tower with no cross-links exposed.",
            "Card 1 — Manual ETA Input (Existing Schedule): Carriers select their truck and submit a live 24-hour ETA update.",
            "Card 2 — Book New Truck Schedule / Appointment: Register a new truck and select a 30m, 45m, or 60m slot duration.",
            "Auto-Syncs to Control Tower: Submissions immediately trigger the 5-Agent pipeline on the main scheduler screen.",
        ],
        "accent": (5, 150, 105),
        "callout": (140, 140, "STANDALONE CARRIER SELF-SERVICE PORTAL (/transport)", (5, 150, 105)),
        "narration": (
            "For external carriers and drivers, we built a dedicated, role-separated Transport Portal. "
            "It gives transport teams two simple self-service tools: submitting a manual 24-hour ETA update for an existing truck, "
            "or booking a brand-new 30, 45, or 60-minute dock appointment — which automatically syncs back to the main Control Tower."
        ),
    },
    {
        "id": "10_demo_committed",
        "badge": "PRODUCT DEMO • PART 7",
        "title": "Human-in-the-Loop Approval & Committed Schedule State",
        "subtitle": "After clicking 'Approve All' — Zero ETA conflicts, all swaps committed to schedule_db.sqlite & truck_db.sqlite",
        "screenshot": "slide_11_approved_committed_schedule.png",
        "layout": "split_demo",
        "card_badge": "ATOMIC EXECUTION OUTCOME",
        "card_title": "Zero Overlaps & Full Alignment",
        "bullets": [
            "Pairwise Slot Swap Committed: TRK-103 (30m) at [08:00–08:30] & TRK-101 (60m) at [10:00–11:00] on DOCK-A.",
            "Cross-Dock Swap Committed: TRK-102 (45m) moved to open DOCK-B [11:00–11:45].",
            "Time Shift & New Booking Committed: TRK-104 (45m) at DOCK-A [13:00–13:45] & TRK-108 (30m) at DOCK-A [09:00–09:30].",
            "Live ETA Conflicts drop from 5 to 0, and dispatch notifications are sent to Master Scheduler and Drivers.",
        ],
        "accent": (37, 99, 235),
        "callout": (240, 290, "ALL PROPOSALS APPROVED & COMMITTED (0 CONFLICTS)", (5, 150, 105)),
        "narration": (
            "Finally, when the warehouse supervisor clicks Approve All, Agent 5 commits every swap and booking across both databases in a single atomic step. "
            "The schedule turns solid blue, live ETA conflicts drop to zero, and automated dispatch notifications go straight out to drivers and the Master Scheduler."
        ),
    },
    {
        "id": "11_benefits_roi",
        "badge": "BENEFITS & ROI",
        "title": "Proposed Business Benefits & Return on Investment",
        "subtitle": "Measurable operational impact across warehouse throughput, detention savings, and audit compliance",
        "screenshot": "slide_11_approved_committed_schedule.png",
        "layout": "benefits",
        "narration": (
            "By combining five autonomous agents with human-in-the-loop control, our solution delivers up to 80 percent faster conflict resolution, "
            "eliminates dock collisions through intelligent Slot Swaps and Cross-Dock balancing, cuts carrier detention costs, "
            "and maintains a 100 percent auditable trail. Thank you for watching!"
        ),
    },
]


def render_chapter_image(idx, total, ch):
    canvas = Image.new("RGB", (W, H), (241, 245, 249))
    draw = ImageDraw.Draw(canvas)

    draw_header(draw, idx, total, ch["badge"], ch["title"], ch["subtitle"])

    layout = ch["layout"]
    img_path = os.path.join(SCREENSHOT_DIR, ch.get("screenshot", "slide_01_control_tower_overview.png"))

    if layout == "hero":
        # Dark slate hero body
        draw.rectangle([0, 148, W, H - 106], fill=(15, 23, 42))
        draw_info_card(
            draw, 48, 184, 650, 748,
            ch["card_badge"], ch["card_title"], ch["bullets"],
            accent=(37, 99, 235), bg=(248, 250, 252)
        )
        paste_screenshot_card(
            canvas, draw, img_path, 736, 184, 1136, 680,
            callout_label=ch.get("callout")
        )
    elif layout == "problem_cards":
        draw_info_card(
            draw, 48, 180, 580, 370,
            "WHY STATIC SCHEDULES FAIL",
            "Operational Bottlenecks",
            [
                "Static dock slots cannot adapt to highway traffic delays, early arrivals, or unbooked trucks.",
                "Overlapping arrival windows [ETA → ETA+Duration] cause bay collisions.",
                "Fragmented silos across TMS, WMS, GPS Telematics & Carriers.",
            ],
            accent=(220, 38, 38),
        )
        draw_info_card(
            draw, 48, 574, 580, 360,
            "BUSINESS IMPACT",
            "Financial & SLA Consequences",
            [
                "Severe yard congestion & cascading dock bay queues.",
                "High carrier detention & demurrage penalties.",
                "Cold-chain (Reefer) spoilage risk & manual spreadsheet rework.",
            ],
            accent=(217, 119, 6),
        )
        paste_screenshot_card(
            canvas, draw, img_path, 664, 180, 1208, 754,
            callout_label=(180, 145, "RED OVERLAPPING ETA COLLISIONS ON DOCK 1 & DOCK 2", (220, 38, 38))
        )
    elif layout == "architecture":
        agents = [
            ("AGENT 01", "TruckDataAgent", "Loads fleet manifest, cargo (Reefer/Dry/Flatbed), weight & 30/45/60m duration from TMS.", (37, 99, 235)),
            ("AGENT 02", "ScheduleDataAgent", "Loads 24-hr slot occupancy (00:00–24:00) & bay capabilities for DOCK-A & DOCK-B.", (124, 58, 237)),
            ("AGENT 03", "ETAFinderAgent", "Computes Δ variance, live window [ETA → ETA+Dur] & Overlapping ETA Red Indicator.", (220, 38, 38)),
            ("AGENT 04", "SlotCheckingAgent", "Constraint solver for Pairwise Slot Swap, Cross-Dock Swap, Time Shift & Booking.", (217, 119, 6)),
            ("AGENT 05", "ExecutionCommAgent", "Atomic commit across schedule_db.sqlite & truck_db.sqlite + driver dispatches.", (5, 150, 105)),
        ]
        card_w = 348
        for i, (code, name, desc, col) in enumerate(agents):
            cx = 48 + i * (card_w + 21)
            draw_info_card(draw, cx, 178, card_w, 365, code, name, [desc], accent=col)

        draw_info_card(
            draw, 48, 568, 880, 366,
            "DECOUPLED 4-TIER ARCHITECTURE & SRADL CYCLE",
            "Sense • Reason • Act • Decide • Learn",
            [
                "Tier 1 (Portals): Main Control Tower (/) + Isolated Carrier Transport Portal (/transport).",
                "Tier 2 (API Gateway): Python FastAPI server orchestrating live preview & approval endpoints.",
                "Tier 3 (5-Agent Brain): Multi-constraint optimizer evaluating Slot Swaps & Cross-Dock Swaps.",
                "Tier 4 (Storage & Connectors): Dual SQLite DBs + live REST API, SQL URI & Webhook links.",
            ],
            accent=(15, 23, 42),
        )
        paste_screenshot_card(
            canvas, draw, img_path, 960, 568, 912, 366,
            callout_label=(20, 16, "5-AGENT PIPELINE TELEMETRY", (37, 99, 235))
        )
    elif layout == "split_demo":
        paste_screenshot_card(
            canvas, draw, img_path, 48, 180, 1180, 748,
            callout_label=ch.get("callout")
        )
        draw_info_card(
            draw, 1260, 180, 612, 748,
            ch["card_badge"], ch["card_title"], ch["bullets"],
            accent=ch.get("accent", (37, 99, 235))
        )
    elif layout == "benefits":
        metrics = [
            ("Up to 80%", "Faster Conflict Resolution", (37, 99, 235)),
            ("0 Collisions", "Pairwise & Cross-Dock Swaps", (5, 150, 105)),
            ("30 / 45 / 60m", "Flexible Slot Utilization", (124, 58, 237)),
            ("100% Audit", "Dual-DB & Dispatch Logs", (217, 119, 6)),
        ]
        mw = 435
        for i, (m_val, m_lbl, col) in enumerate(metrics):
            mx = 48 + i * (mw + 28)
            draw.rounded_rectangle([mx, 178, mx + mw, 340], radius=16, fill=(15, 23, 42), outline=col, width=3)
            draw.text((mx + mw // 2, 238), m_val, font=FONT_METRIC_VAL, fill=(96, 165, 250), anchor="mm")
            draw.text((mx + mw // 2, 298), m_lbl, font=FONT_METRIC_LBL, fill=(226, 232, 240), anchor="mm")

        draw_info_card(
            draw, 48, 368, 890, 564,
            "KEY BUSINESS BENEFITS & ROI",
            "Why Autonomous Multi-Agent Dock Scheduling Wins",
            [
                "Eliminates Dock Bay Collisions: Pairwise Slot Swaps pair early trucks with delayed trucks on the same dock.",
                "Dynamic Cross-Dock Load Balancing: Automatically moves delayed trucks from occupied DOCK-A slots to open DOCK-B bays.",
                "Reduces Detention & Demurrage Costs: Converts wasted yard waiting time into immediate dock productivity.",
                "Zero-License Open Architecture: Python FastAPI, Vanilla JS 24-Hr Gantt, Dual SQLite DBs & pluggable TMS/WMS connectors.",
            ],
            accent=(5, 150, 105),
        )
        paste_screenshot_card(
            canvas, draw, img_path, 968, 368, 904, 564,
            callout_label=(20, 18, "100% CONFLICT-FREE COMMITTED SCHEDULE", (5, 150, 105))
        )

    draw_subtitle_caption_bar(draw, ch["narration"])

    out_img = os.path.join(VIDEO_BUILD_DIR, f"slide_{idx:02d}.png")
    canvas.save(out_img)
    return out_img


async def synthesize_edge_tts(text, out_audio_path):
    import edge_tts
    import edge_tts.communicate

    edge_tts.communicate._SSL_CTX = False

    last_err = None
    for voice_name in ("en-US-AvaNeural", "en-US-AndrewNeural", "en-US-AriaNeural"):
        try:
            communicate = edge_tts.Communicate(
                text,
                voice=voice_name,
                rate="+0%",
                pitch="+0Hz",
            )
            await communicate.save(out_audio_path)
            if os.path.exists(out_audio_path) and os.path.getsize(out_audio_path) > 1000:
                return voice_name
        except Exception as err:
            last_err = err
    raise RuntimeError(f"All neural voices failed: {last_err}")


def synthesize_sapi_fallback(text, out_wav_path):
    ps_script = f"""
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.Rate = 1
    $synth.SetOutputToWaveFile('{out_wav_path}')
    $synth.Speak({repr(text)})
    $synth.Dispose()
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)


def generate_audio_for_chapter(idx, text, ffmpeg_exe):
    mp3_path = os.path.join(VIDEO_BUILD_DIR, f"neural_{idx:02d}.mp3")
    wav_path = os.path.join(VIDEO_BUILD_DIR, f"neural_{idx:02d}.wav")

    try:
        asyncio.run(synthesize_edge_tts(text, mp3_path))
        subprocess.run(
            [
                ffmpeg_exe, "-y",
                "-i", mp3_path,
                "-af", "apad=pad_dur=0.6",
                "-ar", "44100", "-ac", "2",
                wav_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except Exception as e:
        print(f"Edge TTS fallback to Windows SAPI for chapter {idx}: {e}")
        raw_wav = os.path.join(VIDEO_BUILD_DIR, f"raw_{idx:02d}.wav")
        synthesize_sapi_fallback(text, raw_wav)
        subprocess.run(
            [
                ffmpeg_exe, "-y",
                "-i", raw_wav,
                "-af", "apad=pad_dur=0.6",
                "-ar", "44100", "-ac", "2",
                wav_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    with wave.open(wav_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / float(rate)
    return wav_path, duration


def build_video_segment(idx, img_path, wav_path, duration, ffmpeg_exe):
    seg_path = os.path.join(VIDEO_BUILD_DIR, f"segment_{idx:02d}.mp4")
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-loop", "1",
            "-framerate", "5",
            "-i", img_path,
            "-i", wav_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-preset", "ultrafast",
            "-crf", "20",
            "-r", "24",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", f"{duration:.2f}",
            "-shortest",
            seg_path,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return seg_path


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    print(f"Using ffmpeg binary: {ffmpeg_exe}")

    total = len(CHAPTERS)
    segment_files = []
    total_duration = 0.0

    for idx, ch in enumerate(CHAPTERS, 1):
        print(f"[{idx}/{total}] Rendering visual frame & voiceover for '{ch['title']}'...")
        img_path = render_chapter_image(idx, total, ch)
        wav_path, dur = generate_audio_for_chapter(idx, ch["narration"], ffmpeg_exe)
        seg_path = build_video_segment(idx, img_path, wav_path, dur, ffmpeg_exe)
        segment_files.append(seg_path)
        total_duration += dur
        print(f"    -> Segment {idx:02d} ready ({dur:.1f}s)")

    concat_list_path = os.path.join(VIDEO_BUILD_DIR, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for seg in segment_files:
            safe_seg = seg.replace("\\", "/")
            f.write(f"file '{safe_seg}'\n")

    video_filename = "Autonomous_Multi_Agent_Dock_Scheduler_Explainer_Demo.mp4"
    out_project = os.path.join(BASE_DIR, video_filename)
    out_downloads = os.path.join(DOWNLOADS_DIR, video_filename)
    out_static = os.path.join(STATIC_DIR, video_filename)
    out_artifact = os.path.join(ARTIFACT_DIR, video_filename)

    print("Concatenating segments into final Full HD MP4 video...")
    subprocess.run(
        [
            ffmpeg_exe, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            "-movflags", "+faststart",
            out_project,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    shutil.copyfile(out_project, out_downloads)
    shutil.copyfile(out_project, out_static)
    shutil.copyfile(out_project, out_artifact)

    size_mb = os.path.getsize(out_project) / (1024 * 1024)
    print("=" * 72)
    print(f"SUCCESS! Generated Full HD Explainer & Demo Video ({total_duration:.1f}s, {size_mb:.2f} MB):")
    print(f"  1) Downloads : {out_downloads}")
    print(f"  2) Project   : {out_project}")
    print(f"  3) Artifact  : {out_artifact}")
    print("=" * 72)


if __name__ == "__main__":
    main()
