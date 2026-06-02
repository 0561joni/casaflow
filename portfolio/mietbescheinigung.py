from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


TEMPLATE_DIR = Path(settings.BASE_DIR) / "portfolio" / "document_templates"
STADT_KASSEL_TEMPLATE = TEMPLATE_DIR / "stadt_kassel_mietbescheinigung.pdf"
JOBCENTER_SOURCE_DOCX = TEMPLATE_DIR / "jobcenter_mietbescheinigung.docx"


def _money(value: Decimal | int | None) -> str:
    value = Decimal(value or 0)
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _date(value: date | None) -> str:
    if not value:
        return ""
    return value.strftime("%d.%m.%Y")


def _check(c: canvas.Canvas, x: float, y: float, checked: bool):
    c.rect(x, y, 8, 8)
    if checked:
        c.setLineWidth(1.2)
        c.line(x + 1.5, y + 4, x + 3.5, y + 1.5)
        c.line(x + 3.5, y + 1.5, x + 7, y + 7)
        c.setLineWidth(1)


def _draw_text(c: canvas.Canvas, x: float, y: float, text: str, size: int = 9):
    c.setFont("Helvetica", size)
    c.drawString(x, y, str(text or "")[:90])


def _signature_source(data: dict):
    if not data.get("include_signature"):
        return None
    if data.get("signature_bytes"):
        return BytesIO(data["signature_bytes"])
    if data.get("signature_path") and Path(data["signature_path"]).exists():
        return str(data["signature_path"])
    return None


def _draw_signature(c: canvas.Canvas, data: dict, x: float, y: float, max_width: float = 130, max_height: float = 42):
    source = _signature_source(data)
    if not source:
        return
    try:
        image = ImageReader(source)
        width, height = image.getSize()
    except Exception:
        return
    if not width or not height:
        return
    scale = min(max_width / width, max_height / height)
    c.drawImage(image, x, y, width=width * scale, height=height * scale, mask="auto")


def _signature_flowable(data: dict, max_width: float = 140, max_height: float = 46):
    source = _signature_source(data)
    if not source:
        return None
    try:
        image_reader = ImageReader(source)
        width, height = image_reader.getSize()
    except Exception:
        return None
    if not width or not height:
        return None
    scale = min(max_width / width, max_height / height)
    if isinstance(source, BytesIO):
        source.seek(0)
    image = Image(source, width=width * scale, height=height * scale)
    image.hAlign = "LEFT"
    return image


def _overlay_stadt_kassel(data: dict) -> BytesIO:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    _draw_text(c, 165, 708, data["tenant_name"])
    _draw_text(c, 165, 668, f"{data['tenant_street']}, {data['floor']}".strip(", "))
    _draw_text(c, 165, 630, data["tenant_zip"])
    _draw_text(c, 165, 596, data["tenant_city"])
    _draw_text(c, 165, 558, data.get("tenant_contact", ""))
    _draw_text(c, 165, 500, data["landlord_name"])
    _draw_text(c, 165, 462, data["landlord_street"])
    _draw_text(c, 165, 424, data.get("landlord_zip", ""))
    _draw_text(c, 165, 390, data.get("landlord_city", ""))
    _draw_text(c, 165, 352, _contact_line(data))
    _draw_text(c, 438, 420, _date(data["lease_start"]))
    _check(c, 73, 376, not data.get("is_sublease"))
    _check(c, 136, 376, data.get("is_sublease"))
    _draw_text(c, 438, 345, data.get("tenant_count", ""))
    _check(c, 74, 308, data.get("public_funded"))
    _check(c, 161, 308, not data.get("public_funded"))
    _draw_text(c, 186, 254, data.get("living_area_sqm", ""))
    c.showPage()

    _draw_text(c, 145, 731, f"{_money(data['total_rent'])} €")
    _draw_text(c, 145, 692, _date(data["rent_valid_from"]))
    _check(c, 73, 632, data.get("heating_in_total_rent"))
    _check(c, 143, 632, not data.get("heating_in_total_rent"))
    _draw_text(c, 405, 632, f"{_money(data.get('heating_costs'))} €")
    _check(c, 73, 590, data.get("warm_water_in_total_rent"))
    _check(c, 143, 590, not data.get("warm_water_in_total_rent"))
    _draw_text(c, 405, 590, f"{_money(data.get('warm_water_costs'))} €")
    _check(c, 73, 508, data.get("garage_in_total_rent"))
    _check(c, 143, 508, not data.get("garage_in_total_rent"))
    _draw_text(c, 405, 508, f"{_money(data.get('garage_cost'))} €")
    _check(c, 73, 468, data.get("parking_in_total_rent"))
    _check(c, 143, 468, not data.get("parking_in_total_rent"))
    _draw_text(c, 405, 468, f"{_money(data.get('parking_cost'))} €")
    _check(c, 73, 385, data.get("arrears_existing"))
    _check(c, 112, 385, not data.get("arrears_existing"))
    _draw_text(c, 405, 385, f"{_money(data.get('arrears_amount'))} €")
    _check(c, 73, 333, data.get("rent_reduction"))
    _check(c, 112, 333, not data.get("rent_reduction"))
    _draw_text(c, 74, 92, f"{data.get('issue_place', '')}, {_date(data['issue_date'])}")
    _draw_signature(c, data, 335, 75)
    c.save()
    buffer.seek(0)
    return buffer


def _merge_overlay(template_path: Path, overlay: BytesIO) -> bytes:
    template_reader = PdfReader(str(template_path))
    overlay_reader = PdfReader(overlay)
    writer = PdfWriter()
    for index, page in enumerate(template_reader.pages):
        if index < len(overlay_reader.pages):
            page.merge_page(overlay_reader.pages[index])
        writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _contact_line(data: dict) -> str:
    parts = [data.get("landlord_phone", ""), data.get("landlord_fax", ""), data.get("landlord_email", "")]
    return " / ".join(part for part in parts if part)


def _draw_jobcenter_checkbox(value: bool) -> str:
    return "[x]" if value else "[ ]"


def _jobcenter_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=34, leftMargin=34, topMargin=32, bottomMargin=28)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Mietbescheinigung", styles["Title"]))
    story.append(Paragraph("Nach Vorlage Jobcenter - vom Vermieter auszufüllen", styles["Normal"]))
    story.append(Spacer(1, 10))

    rows = [
        ("Vermieter", data["landlord_name"]),
        ("Straße", data["landlord_street"]),
        ("PLZ, Ort", f"{data.get('landlord_zip', '')} {data.get('landlord_city', '')}".strip()),
        ("Telefon / Fax / E-Mail", _contact_line(data)),
        ("Mieter", data["tenant_name"]),
        ("Mietobjekt", f"{data['tenant_zip']} {data['tenant_city']}, {data['tenant_street']}".strip()),
        ("Lage im Gebäude", data.get("floor", "")),
        ("Personen in der Wohnung", data.get("tenant_count", "")),
        ("Baujahr / Gebäudefläche / Wohnfläche", f"{data.get('construction_year') or '-'} / {data.get('building_area_sqm') or '-'} m² / {data.get('living_area_sqm') or '-'} m²"),
        ("Anzahl Zimmer", data.get("rooms") or ""),
        ("Einzug", _date(data["lease_start"])),
        ("Mietverhältnis", f"{_draw_jobcenter_checkbox(not data.get('is_sublease'))} Hauptmieter   {_draw_jobcenter_checkbox(data.get('is_sublease'))} Untermieter"),
    ]
    story.append(_table(rows))
    story.append(Spacer(1, 10))

    rent_rows = [
        ("Grundmiete seit", f"{_date(data['rent_valid_from'])}  -  {_money(data['cold_rent'])} € / Monat"),
        ("Betriebskosten seit", f"{_date(data['rent_valid_from'])}  -  {_money(data['operating_costs'])} € / Monat"),
        ("BKO-Berechnung", f"{_draw_jobcenter_checkbox(data.get('operating_costs_advance'))} Vorausleistung mit jährlicher Abrechnung   {_draw_jobcenter_checkbox(not data.get('operating_costs_advance'))} Pauschale"),
        ("Heizkosten", f"{_money(data.get('heating_costs'))} € / Monat"),
        ("Warmwasser in Heizkosten enthalten", f"{_draw_jobcenter_checkbox(data.get('warm_water_in_total_rent'))} ja   {_draw_jobcenter_checkbox(not data.get('warm_water_in_total_rent'))} nein"),
        ("Gesamtmiete", f"{_money(data['total_rent'])} € / Monat"),
        ("Garage / Stellplatz", f"Garage {_money(data.get('garage_cost'))} € / Stellplatz {_money(data.get('parking_cost'))} €"),
    ]
    story.append(Paragraph("Miete und Kosten", styles["Heading2"]))
    story.append(_table(rent_rows))
    story.append(Spacer(1, 28))
    signature = _signature_flowable(data)
    if signature:
        story.append(signature)
        story.append(Spacer(1, 4))
    story.append(Paragraph(f"{data.get('issue_place', '')}, {_date(data['issue_date'])} &nbsp;&nbsp;&nbsp;&nbsp; ______________________________", styles["Normal"]))
    story.append(Paragraph("Ort, Datum &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Unterschrift Vermieter", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()


def _table(rows: list[tuple[str, str]]) -> Table:
    table = Table(rows, colWidths=[150, 350])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def mietbescheinigung_pdf(template: str, data: dict) -> bytes:
    if template == "stadt_kassel":
        return _merge_overlay(STADT_KASSEL_TEMPLATE, _overlay_stadt_kassel(data))
    return _jobcenter_pdf(data)
