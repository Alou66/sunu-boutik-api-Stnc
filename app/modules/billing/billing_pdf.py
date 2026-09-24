"""Génération PDF des factures au format A4 (endpoint /pdf)."""
import io
from pathlib import Path

from app.modules.billing.billing_model import InvoiceStatus

# Libellé du statut de paiement affiché sous le total.
_STATUS_LABELS = {
    InvoiceStatus.PAID: "PAYÉE",
    InvoiceStatus.PARTIAL: "PARTIELLEMENT PAYÉE",
    InvoiceStatus.UNPAID: "NON PAYÉE",
    InvoiceStatus.CANCELLED: "ANNULÉE",
}


def _build_client_label(client, client_name: str | None) -> str | None:
    if client:
        label = client.name
        if client.phone:
            label += f" - {client.phone}"
        if client.address:
            label += f" - {client.address}"
        return label
    return client_name or "Client Divers"


def build_invoice_pdf(invoice, shop, client) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    client_label = _build_client_label(client, invoice.client_name)

    buffer = io.BytesIO()
    base = getSampleStyleSheet()

    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    els = []

    if shop.logo_path and Path(shop.logo_path).exists():
        els.append(Image(shop.logo_path, width=30 * mm, height=30 * mm, kind="proportional"))
        els.append(Spacer(1, 4 * mm))

    els.append(Paragraph(f"<b>{shop.name}</b>", base["Title"]))
    if shop.address:
        els.append(Paragraph(shop.address, base["Normal"]))
    phones = " - ".join(p for p in [shop.phone, shop.phone2, shop.phone3] if p)
    if phones:
        els.append(Paragraph(f"Tél: {phones}", base["Normal"]))
    if shop.ninea:
        els.append(Paragraph(f"NINEA: {shop.ninea}", base["Normal"]))
    els.append(Spacer(1, 10 * mm))

    els.append(Paragraph(f"<b>Facture N° {invoice.number}</b>", base["Heading2"]))
    els.append(Paragraph(f"Date: {invoice.created_at.strftime('%d/%m/%Y %H:%M')}", base["Normal"]))
    if client_label:
        els.append(Paragraph(f"Client: {client_label}", base["Normal"]))
    els.append(Spacer(1, 6 * mm))

    data = [["Qté", "Article", "Prix U", "Prix T"]]
    for line in invoice.lines:
        data.append([f"{line.quantity:g}", line.product_name, f"{line.unit_price:,.0f}", f"{line.line_total:,.0f}"])
    data.append(["", "", "Total", f"{invoice.total:,.0f} FCFA"])
    total_row = len(data) - 1

    # Récapitulatif de paiement, dérivé de invoice.status / balance_due pour
    # rester cohérent avec le reste de l'application.
    status = invoice.status
    if status in (InvoiceStatus.PAID, InvoiceStatus.PARTIAL):
        data.append(["", "", "Montant payé", f"{invoice.amount_paid:,.0f} FCFA"])
    if status in (InvoiceStatus.PARTIAL, InvoiceStatus.UNPAID):
        data.append(["", "", "Reste à payer", f"{invoice.balance_due:,.0f} FCFA"])

    tbl = Table(data, colWidths=[20 * mm, 90 * mm, 35 * mm, 30 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111111")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, total_row), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, total_row - 1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]))
    els.append(tbl)

    status_style = ParagraphStyle(
        "InvoiceStatus", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=16, leading=20, alignment=TA_CENTER,
    )
    els.append(Spacer(1, 6 * mm))
    els.append(Paragraph(_STATUS_LABELS[status], status_style))

    if invoice.note:
        els.append(Spacer(1, 6 * mm))
        els.append(Paragraph(f"Note: {invoice.note}", base["Normal"]))

    doc.build(els)
    buffer.seek(0)
    return buffer.getvalue()
