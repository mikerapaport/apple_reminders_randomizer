"""Create a readable PDF snapshot of reminders using ReportLab."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

def export_pdf(reminders, destination: str | Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("reportlab"):
            raise RuntimeError(
                "PDF export needs ReportLab. Install it with:\n"
                "  python3 -m pip install -r requirements.txt"
            ) from exc
        raise

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AppTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#243b53")))
    styles.add(ParagraphStyle(name="TaskTitle", parent=styles["Heading3"], spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallText", parent=styles["BodyText"], fontSize=9, leading=12))
    doc = SimpleDocTemplate(str(destination), pagesize=letter, rightMargin=.65*inch, leftMargin=.65*inch, topMargin=.6*inch, bottomMargin=.6*inch)
    story = [Paragraph("Apple Reminders Export", styles["AppTitle"]), Paragraph(f"Exported {datetime.now().astimezone().strftime('%b %d, %Y at %I:%M %p')}", styles["SmallText"]), Spacer(1, 14)]
    for item in reminders:
        state = "Completed" if item.completed else "Open"
        attrs = [f"List: {escape(item.list_name)}", state]
        if item.due_date: attrs.append(f"Due: {escape(item.due_date)}")
        if item.flagged: attrs.append("Flagged")
        if item.priority: attrs.append(f"Priority: {item.priority}")
        if item.tags: attrs.append("Tags: " + ", ".join(escape(tag) for tag in item.tags))
        parts = [Paragraph(escape(item.title) or "(Untitled reminder)", styles["TaskTitle"]), Paragraph(" · ".join(attrs), styles["SmallText"])]
        if item.notes:
            note = escape(item.notes).replace("\n", "<br/>")
            parts.append(Paragraph(note, styles["SmallText"]))
        story.extend([KeepTogether(parts), Spacer(1, 10)])
    doc.build(story)
