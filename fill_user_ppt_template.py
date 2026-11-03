import copy
import os
import shutil
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADED_PPTX = r"C:\Users\2427727\.gemini\antigravity\brain\28d738c2-5a3d-47f9-907e-bddbfc7bf8c1\.user_uploaded\media_1793636672478_d50e2a59.pptx"
SCREENSHOT_DIR = os.path.join(BASE_DIR, "docs", "screenshots")
DOWNLOADS_DIR = r"C:\Users\2427727\Downloads"
STATIC_DIR = os.path.join(BASE_DIR, "static")
ARTIFACT_DIR = r"C:\Users\2427727\.gemini\antigravity\brain\28d738c2-5a3d-47f9-907e-bddbfc7bf8c1"


def set_para_text_preserving_style(paragraph, new_text):
    """Replaces paragraph text while preserving the exact font formatting of the first run."""
    if not paragraph.runs:
        paragraph.text = new_text
        return
    paragraph.runs[0].text = new_text
    for r in paragraph.runs[1:]:
        r.text = ""


def set_two_run_para(paragraph, run0_text, run1_text):
    """Preserves bold label in run 0 and normal value in run 1 (like Slide 2 TextBox 8)."""
    if len(paragraph.runs) >= 2:
        paragraph.runs[0].text = run0_text
        paragraph.runs[1].text = run1_text
        for r in paragraph.runs[2:]:
            r.text = ""
    else:
        set_para_text_preserving_style(paragraph, run0_text + run1_text)


def fill_core_8_slides(prs):
    # =========================================================================
    # SLIDE 1: COVER SLIDE
    # =========================================================================
    s1 = prs.slides[0]
    # Shape 1: Team Name
    set_para_text_preserving_style(s1.shapes[1].text_frame.paragraphs[0], "Team Name: Agentic Logistics Pioneers")
    # Shape 4: Idea Title
    set_para_text_preserving_style(
        s1.shapes[4].text_frame.paragraphs[0],
        "Idea Title: Autonomous Multi-Agent ETA Dock & Slot Scheduler"
    )

    # =========================================================================
    # SLIDE 2: TEAM DETAILS
    # =========================================================================
    s2 = prs.slides[1]
    # Shape 2 Table: Submitter ID & Submitter Name
    tbl_sub = s2.shapes[2].table
    if len(tbl_sub.rows) > 1:
        tbl_sub.cell(1, 0).text = "2427727"
        tbl_sub.cell(1, 1).text = "Shubham"

    # Shape 3 TextBox 8: Idea Title / Account Name / Theme
    tf_s2 = s2.shapes[3].text_frame
    set_two_run_para(
        tf_s2.paragraphs[0],
        "Idea Title\t\t",
        ": Autonomous Multi-Agent ETA Dock & Slot Scheduler"
    )
    set_two_run_para(
        tf_s2.paragraphs[1],
        "Account Name\t",
        ": Enterprise Supply Chain, Warehouse & Yard Operations"
    )
    set_two_run_para(
        tf_s2.paragraphs[2],
        "Theme ",
        "\t\t: Agentic AI for Smart Logistics, Dock Scheduling & Real-Time ETA Optimization"
    )

    # =========================================================================
    # SLIDE 3: BUSINESS SCENARIO
    # =========================================================================
    s3 = prs.slides[2]
    set_para_text_preserving_style(
        s3.shapes[3].text_frame.paragraphs[0],
        "Why today's dock & yard operations fall short"
    )
    tf_s3_bullets = s3.shapes[4].text_frame
    s3_left_lines = [
        "Static dock schedules cannot adapt to live highway delays, early arrivals, or unbooked trucks",
        "Overlapping arrival windows [ETA → ETA + Duration] cause severe bay collisions & yard congestion",
        "Fragmented data silos across TMS (Truck DB), WMS (Schedule DB), GPS Telematics, and Carriers",
        "Master schedulers spend critical hours manually negotiating slot swaps via phone & spreadsheets",
    ]
    for idx, text in enumerate(s3_left_lines):
        if idx < len(tf_s3_bullets.paragraphs):
            set_para_text_preserving_style(tf_s3_bullets.paragraphs[idx], text)

    # Shape 5: Environment banner on right
    tf_s3_env = s3.shapes[5].text_frame
    set_para_text_preserving_style(tf_s3_env.paragraphs[0], "Warehouse, Yard & Distribution Center Operations")
    set_para_text_preserving_style(tf_s3_env.paragraphs[1], "Multi-dock appointment scheduling across TMS, WMS & Live GPS Telematics")

    # Shape 7, 8, 9: Business impact cards
    set_para_text_preserving_style(s3.shapes[7].text_frame.paragraphs[0], "Dock bay collisions & overlapping ETAs")
    set_para_text_preserving_style(s3.shapes[7].text_frame.paragraphs[1], "Delayed trucks collide with subsequent appointments on the same dock")

    set_para_text_preserving_style(s3.shapes[8].text_frame.paragraphs[0], "High carrier detention & wasted bay capacity")
    set_para_text_preserving_style(s3.shapes[8].text_frame.paragraphs[1], "Early trucks wait idle in the yard while vacated dock slots go unused")

    set_para_text_preserving_style(s3.shapes[9].text_frame.paragraphs[0], "Delayed fulfillment & cold-chain SLA risk")
    set_para_text_preserving_style(s3.shapes[9].text_frame.paragraphs[1], "Refrigerated & priority loads face unloading delays and manual bottlenecks")

    # =========================================================================
    # SLIDE 4: OPPORTUNITY
    # =========================================================================
    s4 = prs.slides[3]
    set_para_text_preserving_style(
        s4.shapes[3].text_frame.paragraphs[0],
        "An autonomous 5-agent control tower for real-time dock & slot optimization"
    )
    set_para_text_preserving_style(
        s4.shapes[4].text_frame.paragraphs[0],
        "Transform dock operations from reactive manual firefighting into proactive, autonomous exception management—with five specialized AI agents orchestrated across Truck DB (TMS), Schedule DB (WMS), Live Telematics, and a Carrier Transport Portal."
    )

    # 5 Domain Agent Columns (Shapes 5..14)
    agent_cols = [
        (5, 6, "01 TruckDataAgent", "Ingests fleet manifests, cargo types (Reefer, Dry Van, Flatbed), weights & 30/45/60m appointment durations from TMS."),
        (7, 8, "02 ScheduleDataAgent", "Loads 24-hour (00:00–24:00) dock slot availability & bay capabilities (DOCK-A & DOCK-B) from WMS."),
        (9, 10, "03 ETAFinderAgent", "Calculates Δ arrival variance, live arrival windows [ETA → ETA+Dur] & flags Overlapping ETA Red Indicators."),
        (11, 12, "04 SlotCheckingAgent", "Synthesizes Pairwise Slot Swaps (SLOT_SWAP), Cross-Dock Swaps (DOCK_SWAP), Time Shifts & New Bookings."),
        (13, 14, "05 ExecutionCommAgent", "Atomically commits approved changes across Dual SQLite DBs & dispatches alerts to Master Scheduler & Drivers."),
    ]
    for hdr_idx, body_idx, hdr_txt, body_txt in agent_cols:
        set_para_text_preserving_style(s4.shapes[hdr_idx].text_frame.paragraphs[0], hdr_txt)
        set_para_text_preserving_style(s4.shapes[body_idx].text_frame.paragraphs[0], body_txt)

    set_para_text_preserving_style(
        s4.shapes[15].text_frame.paragraphs[0],
        "Built on a 24-hour scrollable Gantt chart (with frozen track headers & 30/45/60m slots), pluggable TMS/WMS/Telematics connectors, a standalone Carrier Transport Portal (/transport), and human-in-the-loop approval."
    )

    # =========================================================================
    # SLIDE 5: SOLUTION APPROACH
    # =========================================================================
    s5 = prs.slides[4]
    set_para_text_preserving_style(s5.shapes[3].text_frame.paragraphs[0], "SRADL multi-agent execution cycle")

    sradl_boxes = [
        (4, "S  |  Sense", "Ingests fleet manifests, 24-hr dock slots & live GPS/carrier ETAs via TMS, WMS & Telematics links"),
        (5, "R  |  Reason", "Computes Δ variance & detects same-dock collisions: max(Start_A, Start_B) < min(End_A, End_B)"),
        (6, "A  |  Act", "Proposes Pairwise Slot Swaps (SLOT_SWAP), Cross-Dock Swaps (DOCK_SWAP: A↔B) & 30/45/60m bookings"),
        (7, "D  |  Decide", "Human-in-the-loop single-bar or bulk approval on the 24-hr Gantt chart (or auto-execute mode)"),
        (8, "L  |  Learn", "Persists committed swaps, rejection reasons & dispatch audit trail in schedule_db.sqlite"),
    ]
    for shp_idx, title_txt, desc_txt in sradl_boxes:
        set_para_text_preserving_style(s5.shapes[shp_idx].text_frame.paragraphs[0], title_txt)
        set_para_text_preserving_style(s5.shapes[shp_idx].text_frame.paragraphs[1], desc_txt)

    set_para_text_preserving_style(s5.shapes[9].text_frame.paragraphs[0], "Decoupled, 4-tier layered architecture")

    arch_boxes = [
        (10, "Control Tower & /transport", "24-hr scrollable Gantt (frozen labels, red overlap alerts) + isolated Carrier Portal"),
        (12, "FastAPI + 5-Agent Brain", "MultiAgentOrchestrator (Truck, Schedule, ETA, Slot & Execution agents) + constraint solver"),
        (14, "Dual SQLite + Connector Hub", "truck_db.sqlite & schedule_db.sqlite with live REST API, SQL URI & Webhook bindings"),
        (16, "Enterprise TMS / WMS / GPS", "Pluggable links to external Fleet TMS, Warehouse WMS & Samsara/Telematics streams"),
    ]
    for shp_idx, title_txt, desc_txt in arch_boxes:
        set_para_text_preserving_style(s5.shapes[shp_idx].text_frame.paragraphs[0], title_txt)
        set_para_text_preserving_style(s5.shapes[shp_idx].text_frame.paragraphs[1], desc_txt)

    # =========================================================================
    # SLIDE 6: PROPOSED BENEFITS
    # =========================================================================
    s6 = prs.slides[5]
    set_para_text_preserving_style(s6.shapes[3].text_frame.paragraphs[0], "Up to 80%")
    set_para_text_preserving_style(s6.shapes[3].text_frame.paragraphs[1], "faster conflict resolution")
    set_para_text_preserving_style(
        s6.shapes[3].text_frame.paragraphs[2],
        "Overlapping ETAs, early arrivals, and delayed trucks are resolved in seconds via automated Slot & Dock Swaps while Master Schedulers stay in control of approvals."
    )

    set_para_text_preserving_style(s6.shapes[4].text_frame.paragraphs[0], "Eliminates dock bay collisions & idle slots (Pairwise Slot Swap)")
    set_para_text_preserving_style(
        s6.shapes[4].text_frame.paragraphs[1],
        "Swaps early-arriving trucks (e.g., TRK-103 at 08:05) with delayed trucks (e.g., TRK-101 at 10:05) on the same dock, turning idle bays into immediate throughput."
    )

    set_para_text_preserving_style(s6.shapes[5].text_frame.paragraphs[0], "Dynamic Cross-Dock load balancing (DOCK-A ↔ DOCK-B)")
    set_para_text_preserving_style(
        s6.shapes[5].text_frame.paragraphs[1],
        "Automatically re-routes delayed trucks whose target slot is occupied on DOCK-A to open, cargo-compatible bays on DOCK-B while enforcing Reefer/Dry Van/Flatbed rules."
    )

    set_para_text_preserving_style(s6.shapes[6].text_frame.paragraphs[0], "Self-service Carrier Portal (/transport) & full audit trail")
    set_para_text_preserving_style(
        s6.shapes[6].text_frame.paragraphs[1],
        "Carriers submit manual 24-hr ETAs and book 30m/45m/60m appointments without accessing the internal Control Tower, with every decision logged."
    )

    # =========================================================================
    # SLIDE 7: COST & ROI
    # =========================================================================
    s7 = prs.slides[6]
    tf_cost = s7.shapes[5].text_frame
    cost_lines = [
        "Lightweight, zero-license architecture built for rapid deployment:",
        "• Zero proprietary solver or external paid cloud dependencies",
        "• Embedded Dual SQLite DBs (truck_db.sqlite & schedule_db.sqlite)",
        "• Python FastAPI + Vanilla JS 24-Hr Gantt UI (30/45/60m appointments)",
        "• Pluggable Connector Hub binds directly to TMS, WMS & Telematics APIs",
    ]
    for idx, line in enumerate(cost_lines):
        if idx < len(tf_cost.paragraphs):
            set_para_text_preserving_style(tf_cost.paragraphs[idx], line)

    tf_roi = s7.shapes[6].text_frame
    roi_lines = [
        "• Up to 80% reduction in manual rescheduling effort for Master Schedulers",
        "• Lower carrier detention & demurrage fees via proactive Slot & Dock Swaps",
        "• Higher dock utilization across 24-hr horizon with 30m, 45m & 60m slots",
        "• Zero cold-chain spoilage by enforcing Reefer bay rules on DOCK-A",
        "• Complete audit trail of ETA overrides, approvals & driver dispatches",
    ]
    for idx, line in enumerate(roi_lines):
        if idx < len(tf_roi.paragraphs):
            set_para_text_preserving_style(tf_roi.paragraphs[idx], line)


def move_slide_to_index(prs, old_index, new_index):
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    el = slides[old_index]
    xml_slides.remove(el)
    xml_slides.insert(new_index, el)


def add_visual_demo_slide(prs, title_text, subtitle_text, left_img, left_caption, right_img, right_caption):
    # Use layout index matching Slide 3 ('Basic title and content - light')
    light_layout = prs.slides[2].slide_layout
    slide = prs.slides.add_slide(light_layout)

    # Set title if title placeholder exists
    for shp in slide.shapes:
        if shp.is_placeholder and shp.placeholder_format.idx == 0:
            shp.text = title_text
        elif shp.is_placeholder and "Footer" in shp.name:
            shp.text = "© 2026 Cognizant"
        elif shp.is_placeholder and "Content" in shp.name:
            shp.text = ""

    # Subtitle bar
    tb_sub = slide.shapes.add_textbox(Inches(0.50), Inches(1.08), Inches(12.3), Inches(0.35))
    p_sub = tb_sub.text_frame.paragraphs[0]
    p_sub.text = subtitle_text
    p_sub.font.size = Pt(13)
    p_sub.font.bold = True
    p_sub.font.color.rgb = RGBColor(0, 51, 160)

    # Left screenshot & caption card
    slide.shapes.add_picture(left_img, Inches(0.50), Inches(1.52), width=Inches(6.05), height=Inches(3.63))
    card_l = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.50), Inches(5.25), Inches(6.05), Inches(1.45))
    card_l.fill.solid()
    card_l.fill.fore_color.rgb = RGBColor(244, 246, 250)
    card_l.line.color.rgb = RGBColor(203, 213, 225)
    tf_l = card_l.text_frame
    tf_l.word_wrap = True
    for idx, line in enumerate(left_caption):
        p = tf_l.paragraphs[0] if idx == 0 else tf_l.add_paragraph()
        p.text = line
        p.font.size = Pt(11 if idx == 0 else 10)
        p.font.bold = (idx == 0)
        p.font.color.rgb = RGBColor(15, 23, 42) if idx == 0 else RGBColor(51, 65, 85)

    # Right screenshot & caption card
    slide.shapes.add_picture(right_img, Inches(6.78), Inches(1.52), width=Inches(6.05), height=Inches(3.63))
    card_r = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.78), Inches(5.25), Inches(6.05), Inches(1.45))
    card_r.fill.solid()
    card_r.fill.fore_color.rgb = RGBColor(244, 246, 250)
    card_r.line.color.rgb = RGBColor(203, 213, 225)
    tf_r = card_r.text_frame
    tf_r.word_wrap = True
    for idx, line in enumerate(right_caption):
        p = tf_r.paragraphs[0] if idx == 0 else tf_r.add_paragraph()
        p.text = line
        p.font.size = Pt(11 if idx == 0 else 10)
        p.font.bold = (idx == 0)
        p.font.color.rgb = RGBColor(15, 23, 42) if idx == 0 else RGBColor(51, 65, 85)


def main():
    # 1. Generate exact 8-slide filled template
    prs_8 = Presentation(UPLOADED_PPTX)
    fill_core_8_slides(prs_8)

    out_8_project = os.path.join(BASE_DIR, "IEP_Techathon_2026_Dock_Scheduler_Filled.pptx")
    out_8_downloads = os.path.join(DOWNLOADS_DIR, "IEP_Techathon_2026_Dock_Scheduler_Filled.pptx")
    out_8_static = os.path.join(STATIC_DIR, "IEP_Techathon_2026_Dock_Scheduler_Filled.pptx")
    out_8_artifact = os.path.join(ARTIFACT_DIR, "IEP_Techathon_2026_Dock_Scheduler_Filled.pptx")

    prs_8.save(out_8_project)
    shutil.copyfile(out_8_project, out_8_downloads)
    shutil.copyfile(out_8_project, out_8_static)
    shutil.copyfile(out_8_project, out_8_artifact)
    print(f"Saved exact 8-slide filled template: {out_8_downloads}")

    # 2. Generate extended version with live product & scenario screenshots inserted before "Thank you"
    prs_ext = Presentation(UPLOADED_PPTX)
    fill_core_8_slides(prs_ext)

    s1_img = os.path.join(SCREENSHOT_DIR, "slide_01_control_tower_overview.png")
    s2_img = os.path.join(SCREENSHOT_DIR, "slide_02_gantt_24h_frozen_and_overlaps.png")
    s3_slot_gantt = os.path.join(SCREENSHOT_DIR, "slide_03_slot_swap_gantt.png")
    s5_dock_gantt = os.path.join(SCREENSHOT_DIR, "slide_05_dock_swap_gantt.png")
    s9_conn = os.path.join(SCREENSHOT_DIR, "slide_09_db_and_external_connections.png")
    s10_trans = os.path.join(SCREENSHOT_DIR, "slide_10_transport_portal.png")

    add_visual_demo_slide(
        prs_ext,
        "Product Walkthrough: Control Tower & 24-Hr Scrollable Gantt",
        "Live Control Tower UI (/) with 5-Agent Pipeline, Frozen Left Track Headers, 30/45/60m Slots & Red Overlap Indicator",
        s1_img,
        [
            "Executive Control Tower & 5-Agent Telemetry Strip",
            "• Displays Active Fleet, Live ETA Conflicts, Pending Proposals & Dispatches.",
            "• Instant Scenario Switcher: Full Mix, Slot Swap & Dock Swap (A↔B).",
        ],
        s2_img,
        [
            "24-Hr Scrollable Gantt (00:00–24:00) & Overlapping ETA Red Indicator",
            "• Frozen left column keeps '1. Existing Schedule' & '2. Proposed Schedule' pinned.",
            "• Variable 30m/45m/60m bars + red collision alert when live ETAs overlap.",
        ],
    )

    add_visual_demo_slide(
        prs_ext,
        "Live Scenarios: Pairwise Slot Swap & Cross-Dock Swap (A↔B)",
        "Autonomous conflict resolution by Agent 03 (ETAFinderAgent) and Agent 04 (SlotCheckingAgent)",
        s3_slot_gantt,
        [
            "Scenario 1: Pairwise Slot Swap (SLOT_SWAP on DOCK-A)",
            "• TRK-101 (60m, delayed to 10:05) and TRK-103 (30m, early at 08:05) mutually exchange slots on DOCK-A [08:00 ↔ 10:00] with zero bay idle time.",
        ],
        s5_dock_gantt,
        [
            "Scenario 2: Cross-Dock Swap (DOCK_SWAP: DOCK-A → DOCK-B)",
            "• Delayed TRK-102 (ETA 11:05) & TRK-104 (ETA 12:05, overlapping TRK-105) automatically re-route from occupied DOCK-A to open bays on DOCK-B.",
        ],
    )

    add_visual_demo_slide(
        prs_ext,
        "Enterprise Connectors & Standalone Transport Portal (/transport)",
        "Pluggable TMS/WMS/Telematics integration links and role-separated Carrier Self-Service Portal",
        s9_conn,
        [
            "Pluggable DB & External System Connection Links",
            "• Connects Agent 01 (TMS), Agent 02 (WMS) & Agent 03 (Telematics) to SQLite, REST APIs, PostgreSQL URIs or Webhooks with live test & sync.",
        ],
        s10_trans,
        [
            "Standalone Carrier & Driver Transport Portal (/transport)",
            "• Isolated external UI with two cards: 1. Manual 24-Hr ETA Input (Existing Schedule) & 2. Book New Truck Appointment (30m, 45m, or 60m).",
        ],
    )

    # Move the "Thank you" slide (originally index 7) to the very end (index 10)
    move_slide_to_index(prs_ext, 7, len(prs_ext.slides) - 1)

    out_ext_project = os.path.join(BASE_DIR, "IEP_Techathon_2026_Dock_Scheduler_With_Screenshots.pptx")
    out_ext_downloads = os.path.join(DOWNLOADS_DIR, "IEP_Techathon_2026_Dock_Scheduler_With_Screenshots.pptx")
    out_ext_static = os.path.join(STATIC_DIR, "IEP_Techathon_2026_Dock_Scheduler_With_Screenshots.pptx")
    out_ext_artifact = os.path.join(ARTIFACT_DIR, "IEP_Techathon_2026_Dock_Scheduler_With_Screenshots.pptx")

    prs_ext.save(out_ext_project)
    shutil.copyfile(out_ext_project, out_ext_downloads)
    shutil.copyfile(out_ext_project, out_ext_static)
    shutil.copyfile(out_ext_project, out_ext_artifact)
    print(f"Saved 11-slide filled template with screenshots: {out_ext_downloads}")


if __name__ == "__main__":
    main()
