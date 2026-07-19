# apps/commandes/pdf_utils.py
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from django.utils import timezone


# ── Palette ──────────────────────────────────────────────────────────────────

AMBER       = colors.HexColor('#f59e0b')
AMBER_LIGHT = colors.HexColor('#fffbeb')
AMBER_DARK  = colors.HexColor('#b45309')
DARK        = colors.HexColor('#1f2937')
GRAY        = colors.HexColor('#6b7280')
GRAY_LIGHT  = colors.HexColor('#f3f4f6')
WHITE       = colors.white
GREEN       = colors.HexColor('#16a34a')


# ── Styles texte ──────────────────────────────────────────────────────────────

def _styles():
    return {
        'restaurant': ParagraphStyle(
            'restaurant',
            fontName='Helvetica-Bold', fontSize=22,
            textColor=DARK, alignment=TA_LEFT,
            spaceAfter=2,
        ),
        'restaurant_sub': ParagraphStyle(
            'restaurant_sub',
            fontName='Helvetica', fontSize=9,
            textColor=GRAY, alignment=TA_LEFT,
            spaceAfter=0,
        ),
        'recu_label': ParagraphStyle(
            'recu_label',
            fontName='Helvetica-Bold', fontSize=9,
            textColor=AMBER_DARK, alignment=TA_RIGHT,
            spaceAfter=0,
        ),
        'recu_number': ParagraphStyle(
            'recu_number',
            fontName='Helvetica-Bold', fontSize=20,
            textColor=AMBER, alignment=TA_RIGHT,
            spaceAfter=0,
        ),
        'recu_date': ParagraphStyle(
            'recu_date',
            fontName='Helvetica', fontSize=9,
            textColor=GRAY, alignment=TA_RIGHT,
            spaceAfter=0,
        ),
        'section_title': ParagraphStyle(
            'section_title',
            fontName='Helvetica-Bold', fontSize=8,
            textColor=GRAY, spaceAfter=4,
            spaceBefore=0,
        ),
        'info_label': ParagraphStyle(
            'info_label',
            fontName='Helvetica-Bold', fontSize=9,
            textColor=GRAY,
        ),
        'info_value': ParagraphStyle(
            'info_value',
            fontName='Helvetica', fontSize=9,
            textColor=DARK,
        ),
        'total_label': ParagraphStyle(
            'total_label',
            fontName='Helvetica-Bold', fontSize=12,
            textColor=WHITE,
        ),
        'total_value': ParagraphStyle(
            'total_value',
            fontName='Helvetica-Bold', fontSize=14,
            textColor=WHITE, alignment=TA_RIGHT,
        ),
        'footer': ParagraphStyle(
            'footer',
            fontName='Helvetica', fontSize=8,
            textColor=GRAY, alignment=TA_CENTER,
            leading=14,
        ),
        'footer_bold': ParagraphStyle(
            'footer_bold',
            fontName='Helvetica-Bold', fontSize=9,
            textColor=DARK, alignment=TA_CENTER,
            spaceAfter=2,
        ),
    }


def _fmt_amount(value):
    """Format a number as '25 000 GNF'."""
    return f"{float(value):,.0f} GNF".replace(',', ' ')


def _client_display(commande):
    """Return a human-readable name for who placed the order."""
    if commande.client_nom:
        return commande.client_nom
    try:
        u = commande.table
        if u.nom_complet and not u.is_table():
            return u.nom_complet
        # Rtable — get table number via related_name 'table_restaurant'
        try:
            return f"Table {u.table_restaurant.numero_table}"
        except Exception:
            return u.login
    except Exception:
        return "—"


def _type_label(commande):
    labels = {
        'sur_table':  'Sur table',
        'livraison':  'Livraison à domicile',
        'emporter':   'À emporter',
    }
    return labels.get(commande.type_commande, commande.get_type_commande_display())


def _paiement_label(commande):
    labels = {
        'livraison':    'Paiement à la livraison',
        'orange_money': 'Orange Money',
        'mtn':          'MTN Mobile Money',
        'carte':        'Carte bancaire',
        'paydunya':     'PayDunya',
    }
    return labels.get(commande.mode_paiement, commande.mode_paiement or '—')


# ── Générateur principal ──────────────────────────────────────────────────────

def generer_recu_pdf(commande):
    buffer = BytesIO()
    PAGE_W, PAGE_H = A4
    M = 20 * mm
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M, bottomMargin=M,
    )

    W = PAGE_W - 2 * M          # usable width ≈ 170mm
    s = _styles()
    elements = []

    resto     = commande.restaurant
    resto_nom = resto.nom if resto else "Restaurant"

    # ── En-tête : nom restaurant (gauche) + numéro reçu (droite) ─────────────
    # On utilise des Paragraphs avec <br/> — pas de listes dans les cellules.
    sub_lines = []
    if resto and resto.adresse:
        sub_lines.append(resto.adresse)
    if resto and resto.telephone:
        sub_lines.append(resto.telephone)
    sub_html = ("<br/>" + "<br/>".join(sub_lines)) if sub_lines else ""

    left_para = Paragraph(
        f'<font name="Helvetica-Bold" size="22" color="#1f2937">{resto_nom.upper()}</font>'
        f'{sub_html}',
        ParagraphStyle('hdr_left', fontName='Helvetica', fontSize=9,
                       textColor=GRAY, leading=16, spaceAfter=0),
    )

    date_str = commande.date_commande.strftime('%d/%m/%Y à %H:%M')
    right_para = Paragraph(
        f'<font name="Helvetica-Bold" size="9" color="#b45309">REÇU DE PAIEMENT</font><br/>'
        f'<font name="Helvetica-Bold" size="22" color="#f59e0b">#{commande.id}</font><br/>'
        f'<font name="Helvetica" size="9" color="#6b7280">{date_str}</font>',
        ParagraphStyle('hdr_right', fontName='Helvetica', fontSize=9,
                       alignment=TA_RIGHT, leading=16, spaceAfter=0),
    )

    header_table = Table(
        [[left_para, right_para]],
        colWidths=[W * 0.6, W * 0.4],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING',   (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width=W, thickness=2, color=AMBER, spaceAfter=10))

    # ── Section contextuelle : infos de la commande ───────────────────────────
    is_livraison = commande.type_commande == 'livraison'
    is_emporter  = commande.type_commande == 'emporter'

    info_rows = []

    client_name = _client_display(commande)
    type_label  = _type_label(commande)

    info_rows.append((_label("Type de commande", s), _val(type_label, s)))
    info_rows.append((_label("Client", s), _val(client_name, s)))

    if commande.client_telephone:
        info_rows.append((_label("Téléphone", s), _val(commande.client_telephone, s)))

    if is_livraison and commande.client_adresse_livraison:
        info_rows.append((_label("Adresse de livraison", s), _val(commande.client_adresse_livraison, s)))

    if commande.mode_paiement:
        info_rows.append((_label("Mode de paiement", s), _val(_paiement_label(commande), s)))

    if commande.serveur_ayant_servi and commande.serveur_ayant_servi.nom_complet:
        info_rows.append((_label("Servi par", s), _val(commande.serveur_ayant_servi.nom_complet, s)))
    elif commande.serveur_ayant_servi:
        info_rows.append((_label("Servi par", s), _val(commande.serveur_ayant_servi.login, s)))

    info_table = Table(info_rows, colWidths=[W * 0.38, W * 0.62])
    info_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), GRAY_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (0, -1),  10),
        ('LEFTPADDING',   (1, 0), (1, -1),  8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [GRAY_LIGHT, WHITE]),
        ('LINEBELOW',     (0, 0), (-1, -2), 0.4, colors.HexColor('#e5e7eb')),
        ('ROUNDEDCORNERS', [4]),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 14))

    # ── Tableau des plats ─────────────────────────────────────────────────────
    elements.append(Paragraph("ARTICLES COMMANDÉS", s['section_title']))

    col_plat  = W * 0.50
    col_pu    = W * 0.20
    col_qty   = W * 0.10
    col_total = W * 0.20

    items = commande.items.all()
    sous_total = sum(float(i.sous_total) for i in items)

    plats_header = [
        _th("Désignation"),
        _th("Prix unit.", right=True),
        _th("Qté", center=True),
        _th("Montant", right=True),
    ]
    plats_rows = [plats_header]
    for i, item in enumerate(items):
        bg = GRAY_LIGHT if i % 2 == 0 else WHITE
        plats_rows.append([
            Paragraph(item.plat.nom, ParagraphStyle('pl', fontName='Helvetica', fontSize=9, textColor=DARK)),
            Paragraph(_fmt_amount(item.prix_unitaire), ParagraphStyle('pr', fontName='Helvetica', fontSize=9, textColor=GRAY, alignment=TA_RIGHT)),
            Paragraph(str(item.quantite), ParagraphStyle('pc', fontName='Helvetica', fontSize=9, textColor=DARK, alignment=TA_CENTER)),
            Paragraph(_fmt_amount(item.sous_total), ParagraphStyle('pm', fontName='Helvetica-Bold', fontSize=9, textColor=DARK, alignment=TA_RIGHT)),
        ])

    plats_table = Table(plats_rows, colWidths=[col_plat, col_pu, col_qty, col_total])
    row_bgs = [GRAY_LIGHT if i % 2 == 0 else WHITE for i in range(len(items))]
    plats_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND',    (0, 0), (-1, 0),  AMBER),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('FONTNAME',      (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0),  8),
        ('TOPPADDING',    (0, 0), (-1, 0),  6),
        ('BOTTOMPADDING', (0, 0), (-1, 0),  6),
        # Rows
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [GRAY_LIGHT, WHITE]),
        ('TOPPADDING',    (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('LINEBELOW',     (0, 0), (-1, -1), 0.4, colors.HexColor('#e5e7eb')),
    ]))
    elements.append(plats_table)
    elements.append(Spacer(1, 10))

    # ── Totaux ────────────────────────────────────────────────────────────────
    frais = 0.0
    if is_livraison and resto and resto.frais_livraison:
        frais = float(resto.frais_livraison)

    # Colonnes : [espace vide | libellé | montant]
    COL_EMPTY = W * 0.35
    COL_LABEL = W * 0.42
    COL_AMOUNT = W * 0.23

    _st = lambda t, right=False: Paragraph(t, ParagraphStyle(
        'x', fontName='Helvetica', fontSize=9,
        textColor=GRAY, alignment=TA_RIGHT if right else TA_LEFT,
    ))
    _sv = lambda t: Paragraph(t, ParagraphStyle(
        'y', fontName='Helvetica', fontSize=9,
        textColor=DARK, alignment=TA_RIGHT,
    ))

    total_rows = []
    if frais > 0:
        total_rows.append(["", _st("Sous-total articles"), _sv(_fmt_amount(sous_total))])
        total_rows.append(["", _st("Frais de livraison"),  _sv(_fmt_amount(frais))])

    # Ligne TOTAL (fond ambre, texte blanc)
    total_rows.append([
        "",
        Paragraph("TOTAL", ParagraphStyle('tl', fontName='Helvetica-Bold', fontSize=13, textColor=WHITE)),
        Paragraph(_fmt_amount(commande.montant_total), ParagraphStyle('tv', fontName='Helvetica-Bold', fontSize=13, textColor=WHITE, alignment=TA_RIGHT)),
    ])

    n_sub = len(total_rows) - 1
    totaux_table = Table(total_rows, colWidths=[COL_EMPTY, COL_LABEL, COL_AMOUNT])

    style_total = TableStyle([
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        # Fond blanc sur les lignes sous-total
        ('BACKGROUND',    (0, 0), (-1, max(n_sub - 1, 0)), WHITE),
        # Ligne de séparation avant le total
        ('LINEABOVE',     (1, n_sub), (-1, n_sub), 0.8, colors.HexColor('#d1d5db')),
        # Ligne TOTAL en ambre
        ('BACKGROUND',    (1, n_sub), (-1, n_sub), AMBER),
        ('TOPPADDING',    (1, n_sub), (-1, n_sub), 10),
        ('BOTTOMPADDING', (1, n_sub), (-1, n_sub), 10),
        ('LEFTPADDING',   (1, n_sub), (1, n_sub), 12),
    ])
    totaux_table.setStyle(style_total)
    elements.append(totaux_table)
    elements.append(Spacer(1, 24))

    # ── Pied de page ─────────────────────────────────────────────────────────
    elements.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor('#e5e7eb'), spaceAfter=10))

    if is_emporter:
        note = "Votre commande est prête à être récupérée au comptoir."
    elif is_livraison:
        note = "Merci pour votre commande. Nous espérons vous livrer rapidement !"
    else:
        note = "Merci de votre visite. À très bientôt !"

    elements.append(Paragraph(f"« {note} »", s['footer_bold']))
    elements.append(Paragraph(
        f"{resto_nom}  ·  Reçu généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')}",
        s['footer'],
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ── Helpers internes ──────────────────────────────────────────────────────────

def _label(text, s):
    return Paragraph(text, s['info_label'])


def _val(text, s):
    return Paragraph(text, s['info_value'])


def _th(text, right=False, center=False):
    alignment = TA_RIGHT if right else (TA_CENTER if center else TA_LEFT)
    return Paragraph(
        text.upper(),
        ParagraphStyle(
            'th', fontName='Helvetica-Bold', fontSize=8,
            textColor=WHITE, alignment=alignment,
        ),
    )
