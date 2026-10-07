"""Branded, paginated A4 quotations. No network services are used."""
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                               Spacer, Table, TableStyle)

NAVY = colors.HexColor('#102b3b')
GREEN = colors.HexColor('#23816a')
MUTED = colors.HexColor('#63747c')
PALE = colors.HexColor('#eef5f4')
LINE = colors.HexColor('#dce5e6')


def build_pdf(quote, company, logo_path, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fonts = Path(__file__).parent / 'static/fonts'
    regular, bold = 'Helvetica', 'Helvetica-Bold'
    if (fonts / 'DejaVuSans.ttf').exists():
        regular, bold = 'AGSans', 'AGSansBold'
        if regular not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular, str(fonts / 'DejaVuSans.ttf')))
            pdfmetrics.registerFont(TTFont(bold, str(fonts / 'DejaVuSans-Bold.ttf')))
    base = ParagraphStyle('AGBody', fontName=regular, fontSize=8.5, leading=13, textColor=NAVY, spaceAfter=3, splitLongWords=True)
    small = ParagraphStyle('AGSmall', parent=base, fontSize=7.3, leading=11, textColor=MUTED)
    strong = ParagraphStyle('AGStrong', parent=base, fontName=bold)
    right = ParagraphStyle('AGRight', parent=base, alignment=TA_RIGHT)
    heading = ParagraphStyle('AGHeading', parent=base, fontName=bold, fontSize=27, leading=34)
    label = ParagraphStyle('AGLabel', parent=small, fontName=bold, fontSize=7.5, textColor=GREEN, spaceAfter=6)
    signature = quote.get('theme', 'signature') == 'signature'
    currency = 'TSh' if quote['currency'] == 'TSH' else 'USD'

    def p(value, style=base):
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)

    def cash(value):
        return f'{Decimal(str(value)):,.2f}'

    story = []
    brand = p(company['name'], ParagraphStyle('Brand', parent=strong, fontSize=15, leading=20))
    if logo_path and Path(logo_path).is_file():
        w, h = ImageReader(str(logo_path)).getSize()
        scale = min(145 / w, 74 / h)
        brand = Image(str(logo_path), width=w * scale, height=h * scale, hAlign='LEFT')
    title_block = [p('QUOTATION', heading), p(quote['number'], strong), p(quote.get('title', ''), small)]
    header = Table([[brand, title_block]], colWidths=[280, 231], hAlign='LEFT')
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story += [header, Spacer(1, 14)]
    if signature:
        band = Table([[p('ISSUED', label), p('VALID UNTIL', label), p('CURRENCY', label), p('PRICE LEVEL', label)],
                      [p(quote['issue_date'], strong), p(quote['valid_until'], strong), p(currency, strong), p(quote.get('price_level', 'retail').title(), strong)]],
                     colWidths=[133, 133, 108, 137])
        band.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), PALE), ('TOPPADDING', (0, 0), (-1, 0), 12),
                                 ('BOTTOMPADDING', (0, 0), (-1, 0), 0), ('BOTTOMPADDING', (0, 1), (-1, -1), 12), ('LEFTPADDING', (0, 0), (-1, -1), 12)]))
        story += [band, Spacer(1, 20)]
    else:
        story += [p(f"Issued: {quote['issue_date']}     |     Valid until: {quote['valid_until']}     |     Currency: {currency}", small), Spacer(1, 20)]
    from_block = [p('PREPARED BY', label), p(company['name'], strong), p(company['address']), p(company['location']),
                  p(f"TIN: {company['tin']}  |  VRN: {company['vrn']}", small)]
    for key in ('email', 'phone', 'website'):
        if company.get(key):
            from_block.append(p(company[key], small))
    to_block = [p('PREPARED FOR', label), p(quote['client_name'], strong), p(quote.get('client_address', ''))]
    for key in ('client_email', 'client_phone'):
        if quote.get(key):
            to_block.append(p(quote[key], small))
    parties = Table([[from_block, to_block]], colWidths=[280, 231])
    parties.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 20)]))
    story += [parties, Spacer(1, 20)]
    white = ParagraphStyle('AGWhite', parent=small, fontName=bold, textColor=colors.white)
    headers = ['ITEM / DESCRIPTION', 'QTY', 'UNIT', f'RATE ({currency})', 'VAT', f'AMOUNT ({currency})']
    rows = [[p(t, white if signature else label) for t in headers]]
    for line in quote['lines']:
        description = [p(line['name'], strong)]
        if line.get('description'):
            description.append(p(line['description'], small))
        vat_text = 'No VAT' if quote['vat_mode'] == 'none' else ('Taxable' if line['taxable'] else 'Exempt')
        rows.append([description, p(line['quantity'], right), p(line.get('unit', 'pcs'), small),
                     p(cash(line['unit_price']), right), p(vat_text, small), p(cash(line['listed_amount']), right)])
    items = Table(rows, colWidths=[180, 38, 45, 87, 61, 100], repeatRows=1, hAlign='LEFT')
    items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY if signature else PALE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10), ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('LINEBELOW', (0, 1), (-1, -1), .4, LINE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafb')]),
    ]))
    story += [items, Spacer(1, 15)]
    totals = quote['totals']
    subtotal_label = 'Subtotal (VAT included)' if quote['vat_mode'] == 'inclusive' else 'Subtotal'
    summary = [[p(subtotal_label), p(cash(totals['subtotal']), right)]]
    if Decimal(totals['discount_amount']):
        summary.append([p(f"Discount ({quote['discount']}%)"), p('-' + cash(totals['discount_amount']), right)])
    if quote['vat_mode'] == 'inclusive':
        summary += [[p('Net amount'), p(cash(totals['net']), right)],
                    [p(f"VAT included ({quote['vat_rate']}%)"), p(cash(totals['vat']), right)]]
    elif quote['vat_mode'] == 'exclusive':
        summary.append([p(f"VAT ({quote['vat_rate']}%)"), p(cash(totals['vat']), right)])
    else:
        summary.append([p('VAT'), p('Not applied', right)])
    summary.append([p(f'TOTAL ({currency})', strong), p(cash(totals['total']), ParagraphStyle('Total', parent=right, fontName=bold, fontSize=13, leading=18))])
    summary_table = Table(summary, colWidths=[197, 125], hAlign='RIGHT')
    summary_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 7),
                                       ('BOTTOMPADDING', (0, 0), (-1, -1), 7), ('BACKGROUND', (0, -1), (-1, -1), PALE),
                                       ('LINEABOVE', (0, -1), (-1, -1), 1, GREEN)]))
    story += [KeepTogether([summary_table]), Spacer(1, 22)]
    treatment = {'exclusive': 'Unit prices exclude VAT. VAT applies only to taxable items.',
                 'inclusive': 'Unit prices include VAT where applicable. The VAT portion is shown above.',
                 'none': 'No VAT has been applied to this quotation.'}[quote['vat_mode']]
    story += [p(treatment, small), Spacer(1, 14)]
    for key, title in [('notes', 'NOTES'), ('terms', 'TERMS & CONDITIONS')]:
        if quote.get(key):
            story += [p(title, label), p(quote[key], small), Spacer(1, 10)]
    story += [Spacer(1, 12), p('Thank you for choosing AG Energies.', strong)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(42, 43, A4[0] - 42, 43)
        canvas.setFont(regular, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(42, 30, quote['number'] + '  |  AG Energies')
        canvas.drawRightString(A4[0] - 42, 30, f'Page {doc.page}')
        canvas.restoreState()

    temporary = output_path.with_suffix('.pdf.tmp')
    document = SimpleDocTemplate(str(temporary), pagesize=A4, rightMargin=42, leftMargin=42,
                                 topMargin=36, bottomMargin=62, title=quote['number'], author=company['name'])
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    temporary.replace(output_path)
    return output_path
