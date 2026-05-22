from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from app.utils import euro, fr_date
from app.settings_store import get_company
from app.db import SessionLocal


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="H1", fontName="Helvetica-Bold", fontSize=22, leading=26, spaceAfter=4))
    s.add(ParagraphStyle(name="H2", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#444")))
    s.add(ParagraphStyle(name="Small", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#666")))
    s.add(ParagraphStyle(name="RightSmall", fontName="Helvetica", fontSize=9, leading=11, alignment=TA_RIGHT))
    s.add(ParagraphStyle(name="Body", fontName="Helvetica", fontSize=9.5, leading=12))
    s.add(ParagraphStyle(name="Bold", fontName="Helvetica-Bold", fontSize=10, leading=12))
    return s


def _header_block(doc_type: str, number: str, doc_date, due_date=None):
    """Bloc en-tête à droite avec numéro et dates."""
    rows = [
        [Paragraph(f"<b>{doc_type}</b>", _styles()["H2"])],
        [Paragraph(f"N° <b>{number}</b>", _styles()["Body"])],
        [Paragraph(f"Date : {fr_date(doc_date)}", _styles()["Body"])],
    ]
    if due_date:
        rows.append([Paragraph(f"Échéance : {fr_date(due_date)}", _styles()["Body"])])
    t = Table(rows, colWidths=[60 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#888")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _company_address(company: dict):
    s = _styles()
    lines = [company["name"]]
    if company["address"]:
        lines.extend(company["address"].split("\n"))
    if company["phone"]:
        lines.append(f"Tél : {company['phone']}")
    if company["email"]:
        lines.append(company["email"])
    if company["siret"]:
        lines.append(f"SIRET : {company['siret']}")
    return Paragraph("<br/>".join(lines), s["Small"])


def _client_block(client, address):
    s = _styles()
    lines = [f"<b>{client.name}</b>"] if client else ["<b>—</b>"]
    if client and client.address:
        lines.extend(client.address.split("\n"))
    if address:
        lines.append("")
        lines.append("<i>Chantier :</i>")
        lines.extend(address.split("\n"))
    return Paragraph("<br/>".join(lines), s["Body"])


def _items_table(items):
    s = _styles()
    data = [["Désignation", "Qté", "Unité", "PU HT", "Total HT"]]
    for it in items:
        total = it.quantity * it.unit_price_ht
        data.append([
            Paragraph(it.description.replace("\n", "<br/>"), s["Body"]),
            f"{it.quantity:g}",
            it.unit or "",
            euro(it.unit_price_ht),
            euro(total),
        ])
    t = Table(data, colWidths=[90 * mm, 18 * mm, 18 * mm, 25 * mm, 25 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
    ]))
    return t


def _totals_table(total_ht, tva_rate, total_ttc):
    s = _styles()
    tva = total_ttc - total_ht
    data = [
        ["Total HT", euro(total_ht)],
        [f"TVA {tva_rate:g} %", euro(tva)],
        ["Total TTC", euro(total_ttc)],
    ]
    t = Table(data, colWidths=[35 * mm, 35 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#222")),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#888")),
    ]))
    return t


def _build(doc_type, number, doc_date, due_date, client, chantier_address,
           items, total_ht, tva_rate, total_ttc, notes, footer_extra=None, company=None):
    if company is None:
        # Fallback : récupère depuis la DB
        db = SessionLocal()
        try:
            company = get_company(db)
        finally:
            db.close()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"{doc_type} {number}",
    )
    s = _styles()
    story = []

    # Bloc en-tête : société à gauche, doc info à droite
    header = Table(
        [[_company_address(company), _header_block(doc_type, number, doc_date, due_date)]],
        colWidths=[100 * mm, 70 * mm],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 8 * mm))

    # Bloc client (encadré)
    story.append(Paragraph("<b>Destinataire</b>", s["H2"]))
    client_tbl = Table([[_client_block(client, chantier_address)]], colWidths=[100 * mm])
    client_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbb")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(client_tbl)
    story.append(Spacer(1, 8 * mm))

    # Items
    story.append(_items_table(items))
    story.append(Spacer(1, 4 * mm))
    story.append(_totals_table(total_ht, tva_rate, total_ttc))

    if notes:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("<b>Notes</b>", s["H2"]))
        story.append(Paragraph(notes.replace("\n", "<br/>"), s["Body"]))

    if footer_extra:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(footer_extra, s["Small"]))

    # Mentions légales basiques
    story.append(Spacer(1, 10 * mm))
    mentions = []
    if company.get("rcs"):
        mentions.append(f"RCS : {company['rcs']}")
    if company.get("tva_intra"):
        mentions.append(f"TVA intra. : {company['tva_intra']}")
    if company.get("iban"):
        mentions.append(f"IBAN : {company['iban']}")
    if mentions:
        story.append(Paragraph(" — ".join(mentions), s["Small"]))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def render_devis_pdf(devis) -> bytes:
    client = devis.chantier.client if devis.chantier else None
    addr = devis.chantier.address if devis.chantier else None
    footer = ""
    if devis.validity_date:
        footer = f"Devis valable jusqu'au {fr_date(devis.validity_date)}. Bon pour accord (date et signature) :"
    return _build(
        doc_type="DEVIS",
        number=devis.number,
        doc_date=devis.date,
        due_date=None,
        client=client,
        chantier_address=addr,
        items=devis.items,
        total_ht=devis.total_ht,
        tva_rate=devis.tva_rate,
        total_ttc=devis.total_ttc,
        notes=devis.notes,
        footer_extra=footer,
    )


def render_facture_pdf(facture) -> bytes:
    client = facture.chantier.client if facture.chantier else None
    addr = facture.chantier.address if facture.chantier else None
    paid = facture.paid_amount or 0
    reste = (facture.total_ttc or 0) - paid
    footer = (
        f"Déjà payé : {euro(paid)} — Reste à payer : <b>{euro(reste)}</b>. "
        f"En cas de retard de paiement, des pénalités pourront être appliquées conformément à la loi."
    )
    return _build(
        doc_type="FACTURE",
        number=facture.number,
        doc_date=facture.date,
        due_date=facture.due_date,
        client=client,
        chantier_address=addr,
        items=facture.items,
        total_ht=facture.total_ht,
        tva_rate=facture.tva_rate,
        total_ttc=facture.total_ttc,
        notes=facture.notes,
        footer_extra=footer,
    )
