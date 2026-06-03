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
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


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


def _check(c: canvas.Canvas, x: float, y: float, checked: bool, draw_box: bool = True):
    if not checked and not draw_box:
        return
    c.saveState()
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    if draw_box:
        c.rect(x, y, 8, 8)
    if checked:
        c.setLineWidth(1.2)
        c.line(x + 1.5, y + 4, x + 3.5, y + 1.5)
        c.line(x + 3.5, y + 1.5, x + 7, y + 7)
    c.restoreState()


def _mark_template_check(c: canvas.Canvas, x: float, y: float, checked: bool):
    _check(c, x, y, checked, draw_box=False)


def _fit_text(text: str, max_width: float, font_name: str = "Helvetica", size: int = 9) -> str:
    text = " ".join(str(text or "").split())
    if not max_width or stringWidth(text, font_name, size) <= max_width:
        return text
    ellipsis = "..."
    available = max_width - stringWidth(ellipsis, font_name, size)
    if available <= 0:
        return ""
    fitted = ""
    for char in text:
        if stringWidth(fitted + char, font_name, size) > available:
            return fitted.rstrip() + ellipsis
        fitted += char
    return fitted


def _draw_text(c: canvas.Canvas, x: float, y: float, text: str, size: int = 9, max_width: float = 260, align: str = "left"):
    font_name = "Helvetica"
    value = _fit_text(text, max_width, font_name, size)
    c.saveState()
    c.setFillColor(colors.black)
    c.setFont(font_name, size)
    if align == "right":
        c.drawRightString(x + max_width, y, value)
    else:
        c.drawString(x, y, value)
    c.restoreState()


def _draw_label(c: canvas.Canvas, x: float, y: float, label: str, size: int = 7):
    c.saveState()
    c.setFillColor(colors.HexColor("#4b5563"))
    c.setFont("Helvetica", size)
    c.drawString(x, y, label)
    c.restoreState()


def _draw_field(c: canvas.Canvas, x: float, y: float, width: float, label: str, value: str, size: int = 9):
    _draw_label(c, x, y + 13, label)
    c.saveState()
    c.setStrokeColor(colors.HexColor("#9ca3af"))
    c.line(x, y - 2, x + width, y - 2)
    c.restoreState()
    _draw_text(c, x, y + 1, value, size=size, max_width=width)


def _draw_amount_field(c: canvas.Canvas, x: float, y: float, width: float, label: str, value: Decimal | int | None):
    _draw_field(c, x, y, width, label, f"{_money(value)} EUR / Monat")


def _draw_section_title(c: canvas.Canvas, x: float, y: float, title: str, width: float = 531):
    c.saveState()
    c.setFillColor(colors.HexColor("#e5e7eb"))
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.roundRect(x, y - 4, width, 18, 3, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 7, y + 1, title)
    c.restoreState()


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


def _overlay_stadt_kassel(data: dict) -> BytesIO:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    _draw_text(c, 165, 489, data["tenant_name"], max_width=330)
    _draw_text(c, 92, 468, f"{data['tenant_street']}, {data['floor']}".strip(", "), max_width=205)
    _draw_text(c, 335, 468, data["tenant_zip"], max_width=45)
    _draw_text(c, 420, 468, data["tenant_city"], max_width=100)
    _draw_text(c, 92, 449, data.get("tenant_contact", ""), size=8, max_width=430)
    _draw_text(c, 165, 410, data["landlord_name"], max_width=330)
    _draw_text(c, 92, 389, data["landlord_street"], max_width=205)
    _draw_text(c, 335, 389, data.get("landlord_zip", ""), max_width=45)
    _draw_text(c, 420, 389, data.get("landlord_city", ""), max_width=100)
    _draw_text(c, 92, 368, _contact_line(data), size=8, max_width=430)
    _draw_text(c, 425, 316, _date(data["lease_start"]), max_width=80)
    _mark_template_check(c, 180, 283, not data.get("is_sublease"))
    _mark_template_check(c, 305, 283, data.get("is_sublease"))
    _draw_text(c, 438, 254, data.get("tenant_count", ""), max_width=45)
    _mark_template_check(c, 180, 199, data.get("public_funded"))
    _mark_template_check(c, 305, 199, not data.get("public_funded"))
    _draw_text(c, 410, 174, data.get("living_area_sqm", ""), max_width=50, align="right")
    c.showPage()

    _draw_text(c, 405, 734, _money(data["total_rent"]), max_width=82, align="right")
    _draw_text(c, 405, 711, _date(data["rent_valid_from"]), max_width=82)
    _mark_template_check(c, 76, 662, data.get("heating_in_total_rent"))
    _mark_template_check(c, 130, 662, not data.get("heating_in_total_rent"))
    _draw_text(c, 405, 666, _money(data.get("heating_costs")), max_width=82, align="right")
    _mark_template_check(c, 76, 639, data.get("warm_water_in_total_rent"))
    _mark_template_check(c, 130, 639, not data.get("warm_water_in_total_rent"))
    _draw_text(c, 405, 643, _money(data.get("warm_water_costs")), max_width=82, align="right")
    _mark_template_check(c, 76, 590, data.get("garage_in_total_rent"))
    _mark_template_check(c, 130, 590, not data.get("garage_in_total_rent"))
    _draw_text(c, 405, 598, _money(data.get("garage_cost")), max_width=82, align="right")
    _mark_template_check(c, 76, 566, data.get("parking_in_total_rent"))
    _mark_template_check(c, 130, 566, not data.get("parking_in_total_rent"))
    _draw_text(c, 405, 575, _money(data.get("parking_cost")), max_width=82, align="right")
    _mark_template_check(c, 112, 505, data.get("arrears_existing"))
    _mark_template_check(c, 137, 505, not data.get("arrears_existing"))
    _draw_text(c, 405, 507, _money(data.get("arrears_amount")), max_width=82, align="right")
    _mark_template_check(c, 112, 457, data.get("rent_reduction"))
    _mark_template_check(c, 137, 457, not data.get("rent_reduction"))
    _draw_text(c, 74, 342, f"{data.get('issue_place', '')}, {_date(data['issue_date'])}", max_width=190)
    _draw_signature(c, data, 335, 330)
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


def _draw_jobcenter_checkbox(c: canvas.Canvas, x: float, y: float, label: str, checked: bool, label_width: float = 92):
    _check(c, x, y, checked, draw_box=True)
    _draw_text(c, x + 13, y + 1, label, size=8, max_width=label_width)


def _jobcenter_header(c: canvas.Canvas):
    c.saveState()
    c.setFont("Helvetica-Bold", 17)
    c.drawCentredString(297.5, 806, "Mietbescheinigung")
    c.setFont("Helvetica", 8)
    c.drawCentredString(297.5, 792, "nach Vorlage Jobcenter - vom Vermieter auszufüllen")
    c.setStrokeColor(colors.HexColor("#111827"))
    c.line(32, 782, 563, 782)
    c.restoreState()


def _jobcenter_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    _jobcenter_header(c)

    left = 34
    right = 563
    col_gap = 18
    col_width = (right - left - col_gap) / 2
    left2 = left + col_width + col_gap

    _draw_section_title(c, left, 754, "Vermieter")
    _draw_field(c, left, 727, col_width, "Name, Vorname / Firma", data["landlord_name"])
    _draw_field(c, left, 700, col_width, "Straße", data["landlord_street"])
    _draw_field(c, left, 673, 78, "PLZ", data.get("landlord_zip", ""))
    _draw_field(c, left + 92, 673, col_width - 92, "Ort", data.get("landlord_city", ""))
    _draw_field(c, left, 646, 78, "Telefon", data.get("landlord_phone", ""))
    _draw_field(c, left + 92, 646, 74, "Telefax", data.get("landlord_fax", ""))
    _draw_field(c, left + 180, 646, col_width - 180, "E-Mail", data.get("landlord_email", ""))

    _draw_section_title(c, left2, 754, "Mieter")
    _draw_field(c, left2, 727, col_width, "Name, Vorname", data["tenant_name"])
    _draw_jobcenter_checkbox(c, left2, 698, "Hauptmieter", not data.get("is_sublease"))
    _draw_jobcenter_checkbox(c, left2 + 118, 698, "Untermieter", data.get("is_sublease"))
    _draw_field(c, left2, 673, 60, "Anzahl", data.get("tenant_count", ""))
    _draw_field(c, left2 + 74, 673, col_width - 74, "Telefon / E-Mail", data.get("tenant_contact", ""), size=8)
    _draw_field(c, left2, 646, col_width, "Einzug am", _date(data["lease_start"]))

    _draw_section_title(c, left, 610, "Mietobjekt")
    _draw_field(c, left, 583, 62, "PLZ", data.get("tenant_zip", ""))
    _draw_field(c, left + 76, 583, 130, "Ort", data.get("tenant_city", ""))
    _draw_field(c, left + 220, 583, right - left - 220, "Straße, Hausnummer", data["tenant_street"])
    _draw_field(c, left, 553, 120, "Lage im Gebäude", data.get("floor", ""))
    _draw_field(c, left + 137, 553, 80, "Baujahr", data.get("construction_year") or "")
    _draw_field(c, left + 235, 553, 105, "Gebäudewohnfläche", f"{data.get('building_area_sqm') or ''} m²".strip())
    _draw_field(c, left + 360, 553, 95, "Wohnfläche", f"{data.get('living_area_sqm') or ''} m²".strip())
    _draw_field(c, left + 474, 553, 55, "Zimmer", data.get("rooms") or "")

    _draw_section_title(c, left, 513, "Miete und Betriebskosten")
    _draw_amount_field(c, left, 486, 140, "Grundmiete", data["cold_rent"])
    _draw_field(c, left + 155, 486, 100, "seit", _date(data["rent_valid_from"]))
    _draw_amount_field(c, left + 282, 486, 145, "Betriebskosten", data["operating_costs"])
    _draw_field(c, left + 442, 486, 87, "seit", _date(data["rent_valid_from"]))
    _draw_jobcenter_checkbox(c, left, 456, "Vorausleistung mit jährlicher Abrechnung", data.get("operating_costs_advance"), label_width=190)
    _draw_jobcenter_checkbox(c, left + 235, 456, "Pauschale / keine Abrechnung", not data.get("operating_costs_advance"), label_width=170)
    _draw_jobcenter_checkbox(c, left + 442, 456, "Wasser enthalten", True, label_width=85)

    _draw_section_title(c, left, 423, "Heizkosten, Warmwasser und besondere Anteile")
    _draw_amount_field(c, left, 396, 150, "Heizkosten", data.get("heating_costs"))
    _draw_field(c, left + 166, 396, 96, "seit", _date(data["rent_valid_from"]) if data.get("heating_costs") else "")
    _draw_jobcenter_checkbox(c, left + 285, 398, "in Gesamtmiete enthalten", data.get("heating_in_total_rent"), label_width=130)
    _draw_amount_field(c, left, 365, 150, "Warmwasser", data.get("warm_water_costs"))
    _draw_jobcenter_checkbox(c, left + 166, 367, "in Heizkosten enthalten", data.get("warm_water_in_total_rent"), label_width=126)
    _draw_jobcenter_checkbox(c, left + 335, 367, "nicht enthalten", not data.get("warm_water_in_total_rent"), label_width=90)
    _draw_amount_field(c, left, 334, 130, "Garage", data.get("garage_cost"))
    _draw_jobcenter_checkbox(c, left + 147, 336, "in Gesamtmiete enthalten", data.get("garage_in_total_rent"), label_width=140)
    _draw_amount_field(c, left + 335, 334, 130, "PKW-Stellplatz", data.get("parking_cost"))
    _draw_jobcenter_checkbox(c, left + 482, 336, "enthalten", data.get("parking_in_total_rent"), label_width=48)

    _draw_section_title(c, left, 294, "Gesamtmiete")
    _draw_amount_field(c, left, 267, 160, "Gesamtmiete", data["total_rent"])
    _draw_jobcenter_checkbox(c, left + 200, 269, "Mietrückstände vorhanden", data.get("arrears_existing"), label_width=140)
    _draw_field(c, left + 370, 267, 88, "Rückstand", f"{_money(data.get('arrears_amount'))} EUR")
    _draw_jobcenter_checkbox(c, left + 478, 269, "Minderung", data.get("rent_reduction"), label_width=58)

    _draw_section_title(c, left, 224, "Erklärung")
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawString(left, 202, "Die Angaben wurden nach den in CasaFlow gespeicherten aktuellen Miet- und Objektdaten vorausgefüllt.")
    c.drawString(left, 190, "Bitte prüfen Sie die Angaben vor Weitergabe an das Jobcenter.")

    _draw_field(c, left, 142, 210, "Ort, Datum", f"{data.get('issue_place', '')}, {_date(data['issue_date'])}".strip(", "))
    c.setStrokeColor(colors.HexColor("#9ca3af"))
    c.line(left + 295, 140, right, 140)
    _draw_label(c, left + 295, 155, "Unterschrift Vermieter")
    _draw_signature(c, data, left + 310, 145, max_width=150, max_height=45)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def mietbescheinigung_pdf(template: str, data: dict) -> bytes:
    if template == "stadt_kassel":
        return _merge_overlay(STADT_KASSEL_TEMPLATE, _overlay_stadt_kassel(data))
    return _jobcenter_pdf(data)
