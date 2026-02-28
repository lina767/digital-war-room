from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

router = APIRouter()

# ── Color Palette ──────────────────────────────────────────────────────────
BLACK      = colors.HexColor("#0a0a0a")
BG         = colors.HexColor("#111111")
GREEN      = colors.HexColor("#00ff41")
GREEN_DIM  = colors.HexColor("#00aa2a")
ORANGE     = colors.HexColor("#f97316")
RED        = colors.HexColor("#ef4444")
GREY       = colors.HexColor("#6b7280")
WHITE      = colors.HexColor("#f3f4f6")
DARK_GREY  = colors.HexColor("#1f2937")

def threat_color(level: str) -> colors.HexColor:
    l = (level or "").upper()
    if l == "CRITICAL": return RED
    if l == "HIGH":     return colors.HexColor("#f97316")
    if l == "ELEVATED": return ORANGE
    if l == "LOW":      return GREEN_DIM
    return GREY

# ── Pydantic models ────────────────────────────────────────────────────────
class ScenarioItem(BaseModel):
    description: Optional[str] = None
    probability: Optional[float] = None

class BrentInfo(BaseModel):
    price: Optional[str] = None
    change_pct: Optional[str] = None
    as_of: Optional[str] = None

class FinintData(BaseModel):
    brent: Optional[BrentInfo] = None
    escalation_score: Optional[float] = None
    summary: Optional[str] = None

class GeointData(BaseModel):
    anomaly_count: Optional[int] = 0
    high_confidence_count: Optional[int] = 0
    geoint_score: Optional[float] = 20.0
    summary: Optional[str] = None

class SigintData(BaseModel):
    sigint_score: Optional[float] = 30.0
    summary: Optional[str] = None

class NewsData(BaseModel):
    news_score: Optional[float] = None
    overall_sentiment: Optional[float] = None
    sentiment_label: Optional[str] = None
    top_sources: Optional[List[str]] = []

class ExportRequest(BaseModel):
    conflict: str
    escalation_score: Optional[float] = None
    threat_level: Optional[str] = None
    key_findings: Optional[List[str]] = []
    scenarios: Optional[List[ScenarioItem]] = []
    summary: Optional[str] = None
    finint: Optional[FinintData] = None
    geoint: Optional[GeointData] = None
    sigint: Optional[SigintData] = None
    news: Optional[NewsData] = None


# ── PDF Builder ────────────────────────────────────────────────────────────
def build_pdf(req: ExportRequest) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=15*mm,
        bottomMargin=15*mm,
    )

    W = A4[0] - 40*mm  # usable width

    # Styles
    mono = "Courier"
    sans = "Helvetica"

    def style(name, **kw):
        return ParagraphStyle(name, **kw)

    s_classify = style("classify", fontName=mono, fontSize=8, textColor=RED,
                        alignment=TA_CENTER, spaceAfter=2)
    s_title    = style("title", fontName=mono, fontSize=20, textColor=GREEN,
                        alignment=TA_CENTER, spaceAfter=2)
    s_subtitle = style("subtitle", fontName=mono, fontSize=9, textColor=GREY,
                        alignment=TA_CENTER, spaceAfter=8)
    s_section  = style("section", fontName=mono, fontSize=8, textColor=GREEN_DIM,
                        spaceBefore=10, spaceAfter=4)
    s_body     = style("body", fontName=sans, fontSize=9, textColor=WHITE,
                        leading=14, spaceAfter=4)
    s_finding  = style("finding", fontName=sans, fontSize=8.5, textColor=WHITE,
                        leading=13, spaceAfter=3, leftIndent=8)
    s_meta     = style("meta", fontName=mono, fontSize=7.5, textColor=GREY,
                        spaceAfter=2)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    threat = (req.threat_level or "UNKNOWN").upper()
    score  = req.escalation_score or 0.0
    tc     = threat_color(threat)

    story = []

    # ── Header ──
    story.append(Paragraph("// CLASSIFIED – OSINT INTELLIGENCE BRIEF //", s_classify))
    story.append(Spacer(1, 4))
    story.append(Paragraph("DIGITAL WAR ROOM", s_title))
    story.append(Paragraph(f"CONFLICT ANALYSIS REPORT  ·  {now}", s_subtitle))
    story.append(HRFlowable(width=W, color=GREEN_DIM, thickness=0.5))
    story.append(Spacer(1, 6))

    # ── Threat banner ──
    threat_data = [[
        Paragraph(f"SUBJECT: {req.conflict.upper()}", style("tb1", fontName=mono, fontSize=10, textColor=WHITE)),
        Paragraph(f"THREAT LEVEL: {threat}", style("tb2", fontName=mono, fontSize=10, textColor=tc, alignment=TA_RIGHT)),
        Paragraph(f"ESCALATION SCORE: {score:.1f}/100", style("tb3", fontName=mono, fontSize=10, textColor=ORANGE, alignment=TA_RIGHT)),
    ]]
    t = Table(threat_data, colWidths=[W*0.4, W*0.3, W*0.3])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_GREY),
        ("BOX",        (0,0), (-1,-1), 0.5, GREEN_DIM),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # ── Executive Summary ──
    if req.summary:
        story.append(Paragraph("[ EXECUTIVE SUMMARY ]", s_section))
        story.append(HRFlowable(width=W, color=DARK_GREY, thickness=0.3))
        story.append(Spacer(1, 4))
        story.append(Paragraph(req.summary, s_body))
        story.append(Spacer(1, 6))

    # ── Agent Scores ──
    story.append(Paragraph("[ AGENT SCORES ]", s_section))
    story.append(HRFlowable(width=W, color=DARK_GREY, thickness=0.3))
    story.append(Spacer(1, 4))

    score_rows = [["AGENT", "SCORE", "STATUS"]]
    agents = [
        ("FININT", req.finint.escalation_score if req.finint else None),
        ("GEOINT", req.geoint.geoint_score if req.geoint else None),
        ("SIGINT", req.sigint.sigint_score if req.sigint else None),
        ("NEWS",   req.news.news_score if req.news else None),
    ]
    for name, sc in agents:
        sc_str = f"{sc:.1f}" if sc is not None else "N/A"
        status_str = "ACTIVE" if sc is not None else "OFFLINE"
        score_rows.append([name, sc_str, status_str])

    st = Table(score_rows, colWidths=[W*0.4, W*0.3, W*0.3])
    st.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  DARK_GREY),
        ("TEXTCOLOR",     (0,0), (-1,0),  GREEN),
        ("FONTNAME",      (0,0), (-1,-1), mono),
        ("FONTSIZE",      (0,0), (-1,-1), 8),
        ("TEXTCOLOR",     (0,1), (-1,-1), WHITE),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [BLACK, colors.HexColor("#161616")]),
        ("BOX",           (0,0), (-1,-1), 0.5, GREEN_DIM),
        ("LINEBELOW",     (0,0), (-1,0),  0.5, GREEN_DIM),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    story.append(st)
    story.append(Spacer(1, 10))

    # ── Key Findings ──
    if req.key_findings:
        story.append(Paragraph("[ KEY FINDINGS ]", s_section))
        story.append(HRFlowable(width=W, color=DARK_GREY, thickness=0.3))
        story.append(Spacer(1, 4))
        for i, finding in enumerate(req.key_findings[:10], 1):
            story.append(Paragraph(f"{i:02d}.  {finding}", s_finding))
        story.append(Spacer(1, 6))

    # ── Scenarios ──
    if req.scenarios:
        story.append(Paragraph("[ SCENARIO ASSESSMENT ]", s_section))
        story.append(HRFlowable(width=W, color=DARK_GREY, thickness=0.3))
        story.append(Spacer(1, 4))

        scen_rows = [["PROB", "SCENARIO"]]
        for sc in req.scenarios:
            prob = sc.probability or 0
            pct  = f"{round(prob * 100)}%"
            desc = sc.description or "–"
            scen_rows.append([pct, desc])

        st2 = Table(scen_rows, colWidths=[W*0.12, W*0.88])
        st2.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  DARK_GREY),
            ("TEXTCOLOR",     (0,0), (-1,0),  GREEN),
            ("FONTNAME",      (0,0), (-1,-1), mono),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("TEXTCOLOR",     (0,1), (0,-1),  ORANGE),
            ("TEXTCOLOR",     (1,1), (1,-1),  WHITE),
            ("FONTNAME",      (1,1), (1,-1),  sans),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [BLACK, colors.HexColor("#161616")]),
            ("BOX",           (0,0), (-1,-1), 0.5, GREEN_DIM),
            ("LINEBELOW",     (0,0), (-1,0),  0.5, GREEN_DIM),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 8),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ]))
        story.append(st2)
        story.append(Spacer(1, 10))

    # ── FININT Detail ──
    if req.finint and req.finint.brent:
        story.append(Paragraph("[ FINANCIAL INTELLIGENCE ]", s_section))
        story.append(HRFlowable(width=W, color=DARK_GREY, thickness=0.3))
        story.append(Spacer(1, 4))
        b = req.finint.brent
        story.append(Paragraph(
            f"Brent Crude: <b>{b.price}</b>  ({b.change_pct})  as of {b.as_of}",
            style("finint_body", fontName=sans, fontSize=9, textColor=WHITE, leading=14)
        ))
        if req.finint.summary:
            story.append(Paragraph(req.finint.summary, s_body))
        story.append(Spacer(1, 6))

    # ── Footer ──
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width=W, color=GREEN_DIM, thickness=0.5))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"GENERATED: {now}  ·  DIGITAL WAR ROOM  ·  OSINT ONLY – NOT FOR DISTRIBUTION",
        style("footer", fontName=mono, fontSize=7, textColor=GREY, alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "// UNCLASSIFIED // FOR TRAINING AND RESEARCH PURPOSES ONLY //",
        style("footer2", fontName=mono, fontSize=7, textColor=GREY, alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Endpoint ───────────────────────────────────────────────────────────────
@router.post("/export/pdf")
def export_pdf(req: ExportRequest):
    pdf_bytes = build_pdf(req)
    filename  = f"intel_brief_{req.conflict.replace(' ', '_').replace('-', '_').lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
