# apps/commandes/pdf_utils.py
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from django.utils import timezone


def generer_recu_pdf(commande):
    buffer = BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm,  bottomMargin=20*mm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=22, textColor=colors.HexColor('#2563eb'),
        alignment=TA_CENTER, spaceAfter=6,
    )
    center_style = ParagraphStyle(
        'Center', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#6b7280'),
        alignment=TA_CENTER,
    )
    header_style = ParagraphStyle(
        'Header', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#1f2937'), spaceAfter=6,
    )

    elements = []
    restaurant_nom = commande.restaurant.nom if commande.restaurant else "Restaurant"

    # En-tête
    elements.append(Paragraph(restaurant_nom.upper(), title_style))
    elements.append(Paragraph('Système de Gestion de Restaurant', center_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph('─' * 60, center_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph('<b>REÇU DE COMMANDE</b>', header_style))

    # Infos commande
    info_data = [
        ['Numéro :', f'#{commande.id}'],
        ['Date :', commande.date_commande.strftime('%d/%m/%Y à %H:%M')],
        ['Table :', commande.table.login],
        ['Statut :', commande.get_statut_display()],
    ]
    if commande.serveur_ayant_servi:
        info_data.append(['Servi par :', commande.serveur_ayant_servi.login])
    if commande.cuisinier_ayant_prepare:
        info_data.append(['Préparé par :', commande.cuisinier_ayant_prepare.login])

    info_table = Table(info_data, colWidths=[130, 290])
    info_table.setStyle(TableStyle([
        ('FONTNAME',  (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE',  (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6b7280')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 16))

    # Détail plats
    elements.append(Paragraph('<b>DÉTAIL</b>', header_style))
    elements.append(Spacer(1, 6))

    plats_data = [['Plat', 'Prix Unit.', 'Qté', 'Total']]
    for item in commande.items.all():
        plats_data.append([
            item.plat.nom,
            f'{float(item.prix_unitaire):,.0f} GNF'.replace(',', ' '),
            str(item.quantite),
            f'{float(item.sous_total):,.0f} GNF'.replace(',', ' '),
        ])

    plats_table = Table(plats_data, colWidths=[220, 85, 40, 105])
    plats_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 11),
        ('ALIGN',         (1, 1), (-1, -1), 'RIGHT'),
        ('ALIGN',         (2, 1), (2, -1), 'CENTER'),
        ('FONTSIZE',      (0, 1), (-1, -1), 10),
        ('GRID',          (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND',    (0, 1), (-1, -1), colors.whitesmoke),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
    ]))
    elements.append(plats_table)
    elements.append(Spacer(1, 12))

    # Total
    total_data = [['', '', 'TOTAL :', f'{float(commande.montant_total):,.0f} GNF'.replace(',', ' ')]]
    total_table = Table(total_data, colWidths=[200, 85, 80, 85])
    total_table.setStyle(TableStyle([
        ('BACKGROUND',    (2, 0), (-1, 0), colors.HexColor('#059669')),
        ('TEXTCOLOR',     (2, 0), (-1, 0), colors.white),
        ('FONTNAME',      (2, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (2, 0), (-1, 0), 13),
        ('ALIGN',         (2, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING',    (2, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (2, 0), (-1, 0), 10),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 24))

    # Pied de page
    elements.append(Paragraph('─' * 60, center_style))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        f'Merci de votre visite !<br/>{restaurant_nom}<br/>'
        f'Reçu généré le {timezone.now().strftime("%d/%m/%Y à %H:%M")}',
        center_style
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer