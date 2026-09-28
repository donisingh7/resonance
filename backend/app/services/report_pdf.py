from pathlib import Path
from xml.sax.saxutils import escape as _escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.project import Project
from app.models.report import ExecutiveReport


def _bullets(items: list[str], style: ParagraphStyle):
    if not items:
        return Paragraph("<i>None.</i>", style)
    return ListFlowable(
        [ListItem(Paragraph(_escape(item), style)) for item in items],
        bulletType="bullet",
        leftIndent=14,
    )


def render_report_pdf(report: ExecutiveReport, project: Project, output_path: Path) -> Path:
    """Renders an ExecutiveReport to a PDF at output_path using reportlab.

    Every dynamic string is XML-escaped before being embedded in a
    Paragraph, since reportlab's Paragraph markup is a small XML dialect —
    an unescaped `&`/`<`/`>` in real evidence/filename text would otherwise
    raise a parse error and crash report generation.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    heading = styles["Heading2"]
    title_style = styles["Title"]
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.grey)

    doc = SimpleDocTemplate(str(output_path), pagesize=LETTER)
    story = []

    story.append(Paragraph(f"Executive Report — {_escape(project.name)}", title_style))
    story.append(
        Paragraph(
            f"Generated: {report.created_at.isoformat()} &middot; "
            f"Provider: {_escape(report.provider)} &middot; Report id: {_escape(report.id)}",
            small,
        )
    )
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Executive Summary", heading))
    story.append(Paragraph(_escape(report.executive_summary or "N/A"), body))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Source / Asset Coverage", heading))
    coverage_rows = [["Metric", "Value"]] + [
        [_escape(str(k)), _escape(str(v))] for k, v in report.source_coverage.items()
    ]
    table = Table(coverage_rows, colWidths=[2.5 * inch, 3.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Overall Sentiment", heading))
    story.append(Paragraph(_escape(report.overall_sentiment or "N/A"), body))
    story.append(Spacer(1, 0.15 * inch))

    for title, items in [
        ("Top Themes", report.top_themes),
        ("Key Pain Points", report.pain_points),
        ("Positive Signals", report.positive_signals),
        ("Questions / Concerns", report.questions_or_concerns),
        ("Opportunities", report.opportunities),
        ("Recommended Actions", report.recommended_actions),
    ]:
        story.append(Paragraph(title, heading))
        story.append(_bullets(items, body))
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Supporting Evidence", heading))
    if not report.evidence:
        story.append(Paragraph("<i>No evidence items available.</i>", body))
    else:
        for item in report.evidence:
            story.append(
                Paragraph(
                    f"<b>[{_escape(item.category)}]</b> {_escape(item.statement)}<br/>"
                    f"<font size=8 color='grey'>Source: {_escape(item.source_filename)} "
                    f"&middot; asset_id={_escape(item.asset_id)} "
                    f"&middot; processing_result_id={_escape(item.processing_result_id)}</font>",
                    body,
                )
            )
            if item.excerpt:
                story.append(Paragraph(f"<i>&ldquo;{_escape(item.excerpt)}&rdquo;</i>", small))
            story.append(Spacer(1, 0.08 * inch))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Follow-up Questionnaire", heading))
    if report.questionnaire_summary:
        qs = report.questionnaire_summary
        story.append(
            Paragraph(
                f"Questionnaire {_escape(qs.questionnaire_id)} &mdash; {qs.question_count} "
                f"question(s), status: {_escape(qs.status)}.",
                body,
            )
        )
    else:
        story.append(Paragraph("<i>No questionnaire generated yet.</i>", body))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Risk / Moderation / Data-Quality Flags", heading))
    if not report.risk_flags:
        story.append(Paragraph("<i>No flags raised.</i>", body))
    else:
        for flag in report.risk_flags:
            story.append(
                Paragraph(
                    f"<b>[{_escape(flag.severity.value.upper())}] {_escape(flag.code)}</b>: "
                    f"{_escape(flag.message)}",
                    body,
                )
            )
            story.append(Spacer(1, 0.05 * inch))

    doc.build(story)
    return output_path
