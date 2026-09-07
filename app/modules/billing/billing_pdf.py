"""Génération PDF des factures — copiée depuis app/routers/invoices.py.

Deux générateurs distincts et volontairement NON fusionnés : `build_export_ticket_pdf`
(utilisé par l'export ZIP en masse) et `build_invoice_pdf` (utilisé par l'endpoint
/pdf, formats ticket et A4). Ils se ressemblent mais ne sont pas identiques
(styles, libellés de bas de page différents) — les fusionner est un choix de
conception à part, pas un sous-produit d'une migration.
"""
import io
from pathlib import Path


def _build_client_label(client, client_name: str | None) -> str | None:
    if client:
        label = client.name
        if client.phone:
            label += f" - {client.phone}"
        if client.address:
            label += f" - {client.address}"
        return label
    return client_name or None


def build_export_ticket_pdf(invoice, shop, client) -> bytes:
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    client_label = _build_client_label(client, invoice.client_name)

    base_styles = getSampleStyleSheet()
    buf = io.BytesIO()
    W = 76 * mm
    H = (55 + len(invoice.lines) * 8 + (6 if invoice.note else 0) + 20) * mm
    margin = 3 * mm

    center_s = ParagraphStyle("c", parent=base_styles["Normal"], alignment=TA_CENTER, fontSize=8, leading=10)
    bold_c = ParagraphStyle("bc", parent=center_s, fontName="Helvetica-Bold", fontSize=9)
    small = ParagraphStyle("s", parent=base_styles["Normal"], fontSize=7, leading=9)

    doc = SimpleDocTemplate(buf, pagesize=(W, H),
                            topMargin=margin, bottomMargin=margin,
                            leftMargin=margin, rightMargin=margin)
    els = []

    if shop:
        if shop.logo_path and Path(shop.logo_path).exists():
            from reportlab.platypus import Image
            els.append(Image(shop.logo_path, width=15*mm, height=15*mm, kind="proportional"))
        els.append(Paragraph(f"<b>{shop.name}</b>", bold_c))
        if shop.address:
            els.append(Paragraph(shop.address, center_s))
        phones = " - ".join(p for p in [shop.phone, shop.phone2, shop.phone3] if p)
        if phones:
            els.append(Paragraph(f"Tél: {phones}", center_s))
        if shop.ninea:
            els.append(Paragraph(f"NINEA: {shop.ninea}", center_s))

    els.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.black, spaceAfter=2, spaceBefore=2))
    els.append(Paragraph(f"<b>Facture N° {invoice.number}</b>", bold_c))
    els.append(Paragraph(invoice.created_at.strftime("%d/%m/%Y %H:%M"), center_s))
    if client_label:
        els.append(Paragraph(f"Client: {client_label}", small))
    els.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.black, spaceAfter=2, spaceBefore=2))

    inner_w = W - 2 * margin
    data = [["Qté", "Article", "Prix U", "Prix T"]]
    for line in invoice.lines:
        data.append([f"{line.quantity:g}", line.product_name, f"{line.unit_price:,.0f}", f"{line.line_total:,.0f}"])
    data.append(["", "", "TOTAL", f"{invoice.total:,.0f} F"])

    tbl = Table(data, colWidths=[inner_w*0.15, inner_w*0.45, inner_w*0.20, inner_w*0.20])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, rl_colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, rl_colors.black),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, rl_colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    els.append(tbl)

    if invoice.note:
        els.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.black, spaceAfter=2, spaceBefore=2))
        els.append(Paragraph(invoice.note, small))

    els.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.black, spaceAfter=2, spaceBefore=2))
    els.append(Paragraph("Merci de votre confiance !", center_s))
    doc.build(els)
    return buf.getvalue()


def build_invoice_pdf(invoice, shop, client, format: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    client_label = _build_client_label(client, invoice.client_name)

    buffer = io.BytesIO()
    base = getSampleStyleSheet()

    if format == "ticket":
        # 80mm thermal receipt format
        W = 76 * mm
        n_lines = len(invoice.lines)
        H = (55 + n_lines * 8 + (6 if invoice.note else 0) + 20) * mm
        page_size = (W, H)
        margin = 3 * mm

        center = ParagraphStyle("center", parent=base["Normal"], alignment=TA_CENTER, fontSize=8, leading=10)
        bold_center = ParagraphStyle("bold_center", parent=center, fontName="Helvetica-Bold", fontSize=9)
        small = ParagraphStyle("small", parent=base["Normal"], fontSize=7, leading=9)
        small_right = ParagraphStyle("small_right", parent=small, alignment=TA_RIGHT)
        bold_small = ParagraphStyle("bold_small", parent=small, fontName="Helvetica-Bold", fontSize=8)
        bold_right = ParagraphStyle("bold_right", parent=bold_small, alignment=TA_RIGHT)

        doc = SimpleDocTemplate(buffer, pagesize=page_size,
                                topMargin=margin, bottomMargin=margin,
                                leftMargin=margin, rightMargin=margin)
        els = []

        if shop.logo_path and Path(shop.logo_path).exists():
            els.append(Image(shop.logo_path, width=15 * mm, height=15 * mm, kind="proportional"))
        els.append(Paragraph(f"<b>{shop.name}</b>", bold_center))
        if shop.address:
            els.append(Paragraph(shop.address, center))
        phones = " - ".join(p for p in [shop.phone, shop.phone2, shop.phone3] if p)
        if phones:
            els.append(Paragraph(f"Tél: {phones}", center))
        if shop.ninea:
            els.append(Paragraph(f"NINEA: {shop.ninea}", center))
        els.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, spaceAfter=2, spaceBefore=2))

        els.append(Paragraph(f"<b>Facture N° {invoice.number}</b>", bold_center))
        els.append(Paragraph(invoice.created_at.strftime("%d/%m/%Y %H:%M"), center))
        if client_label:
            els.append(Paragraph(f"Client: {client_label}", small))
        els.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, spaceAfter=2, spaceBefore=2))

        inner_w = W - 2 * margin
        col1 = inner_w * 0.15
        col2 = inner_w * 0.45
        col3 = inner_w * 0.20
        col4 = inner_w * 0.20

        data = [["Qté", "Article", "Prix U", "Prix T"]]
        for line in invoice.lines:
            data.append([f"{line.quantity:g}", line.product_name, f"{line.unit_price:,.0f}", f"{line.line_total:,.0f}"])
        data.append(["", "", "TOTAL", f"{invoice.total:,.0f} F"])

        tbl = Table(data, colWidths=[col1, col2, col3, col4])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("LEADING", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        els.append(tbl)

        if invoice.note:
            els.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, spaceAfter=2, spaceBefore=2))
            els.append(Paragraph(invoice.note, small))

        els.append(HRFlowable(width="100%", thickness=0.5, color=colors.black, spaceAfter=2, spaceBefore=2))
        els.append(Paragraph("Merci pour votre achat !", center))

    else:
        # A4 format (original)
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

        tbl = Table(data, colWidths=[20 * mm, 90 * mm, 35 * mm, 30 * mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f3f4f6")]),
        ]))
        els.append(tbl)

        if invoice.note:
            els.append(Spacer(1, 6 * mm))
            els.append(Paragraph(f"Note: {invoice.note}", base["Normal"]))

    doc.build(els)
    buffer.seek(0)
    return buffer.getvalue()
