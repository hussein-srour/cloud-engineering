"""Understated, paginated A4 quotations and bills of quantities."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape

from PIL import Image as PillowImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, Image, KeepTogether, Paragraph,
                               SimpleDocTemplate, Spacer, Table, TableStyle)

INK = colors.HexColor('#303633')
MUTED = colors.HexColor('#747976')
GREEN = colors.HexColor('#789584')
PALE = colors.HexColor('#f4f5f4')
LINE = colors.HexColor('#d8dcd9')


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

    # The legacy theme values remain compatible with saved documents.
    monochrome = quote.get('theme', 'signature') == 'minimal'
    ink = colors.HexColor('#333333') if monochrome else INK
    muted = colors.HexColor('#777777') if monochrome else MUTED
    line_color = colors.HexColor('#d9d9d9') if monochrome else LINE
    pale = colors.HexColor('#f4f4f4') if monochrome else PALE
    accent = line_color if monochrome else GREEN
    base = ParagraphStyle('AGBody', fontName=regular, fontSize=8.7, leading=13,
                          textColor=ink, spaceAfter=2, splitLongWords=True)
    small = ParagraphStyle('AGSmall', parent=base, fontSize=7.7, leading=11.5,
                           textColor=muted)
    strong = ParagraphStyle('AGStrong', parent=base, fontName=bold)
    right = ParagraphStyle('AGRight', parent=base, alignment=TA_RIGHT)
    small_right = ParagraphStyle('AGSmallRight', parent=small, alignment=TA_RIGHT)
    heading = ParagraphStyle('AGHeading', parent=right, fontSize=20, leading=26,
                             spaceAfter=0)
    label = ParagraphStyle('AGLabel', parent=small, fontSize=7.7, leading=12,
                           spaceAfter=4)
    total_label = ParagraphStyle('AGTotalLabel', parent=strong, fontSize=10, leading=15)
    total_right = ParagraphStyle('AGTotalRight', parent=right, fontName=bold,
                                 fontSize=10, leading=15)
    currency = 'TSh' if quote['currency'] == 'TSH' else 'USD'
    is_boq = quote.get('document_type', 'quotation') == 'boq'
    document_title = 'Bill of quantities' if is_boq else 'Quotation'
    number_label = 'BOQ no.' if is_boq else 'Quotation no.'
    # SimpleDocTemplate's frame includes six points of padding on each side.
    width = A4[0] - 96

    def p(value, style=base):
        return Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)

    def cash(value):
        return f'{Decimal(str(value)):,.2f}'

    left_header = []
    if logo_path and Path(logo_path).is_file():
        w, h = ImageReader(str(logo_path)).getSize()
        scale = min(112 / w, 56 / h)
        logo_source = str(logo_path)
        if monochrome:
            with PillowImage.open(logo_path) as original:
                original = original.convert('RGBA')
                gray = ImageOps.grayscale(original).convert('RGBA')
                gray.putalpha(original.getchannel('A'))
                logo_source = BytesIO()
                gray.save(logo_source, format='PNG')
                logo_source.seek(0)
        left_header += [Image(logo_source, width=w * scale, height=h * scale,
                              hAlign='LEFT'), Spacer(1, 8)]
    left_header += [p(company['name']), p(company['address'], small),
                    p(company['location'], small),
                    p(f"TIN: {company['tin']}  |  VRN: {company['vrn']}", small)]
    for key in ('email', 'phone', 'website'):
        if company.get(key):
            left_header.append(p(company[key], small))

    metadata = Table([
        [p(number_label, small), p(quote['number'], small_right)],
        [p('Issue date', small), p(quote['issue_date'], small_right)],
        [p('Valid until', small), p(quote['valid_until'], small_right)],
        [p('Currency', small), p(currency, small_right)],
    ], colWidths=[77, 126], hAlign='RIGHT')
    metadata.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    right_header = [p(document_title, heading), Spacer(1, 14), metadata]
    header = Table([[left_header, right_header]], colWidths=[width - 203, 203],
                   hAlign='LEFT')
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story = [header, Spacer(1, 16),
             HRFlowable(width='100%', thickness=.6, color=accent), Spacer(1, 16)]

    client = [p('Prepared for', label), p(quote['client_name']),
              p(quote.get('client_address', ''), small)]
    for key in ('client_email', 'client_phone'):
        if quote.get(key):
            client.append(p(quote[key], small))
    story += [KeepTogether(client), Spacer(1, 13)]
    if quote.get('title'):
        story += [p(quote['title']), Spacer(1, 9)]
    if quote.get('reference'):
        story += [p(f"Reference: {quote['reference']}", small), Spacer(1, 9)]

    headers = ['No.', 'Description', 'Qty', 'Unit',
               f'Unit price ({currency})', f'Amount ({currency})']
    rows = [[p(text, small_right if index in (2, 4, 5) else small)
             for index, text in enumerate(headers)]]
    for index, item in enumerate(quote['lines'], 1):
        description = [p(item['name'])]
        if item.get('description'):
            description.append(p(item['description'], small))
        if quote['vat_mode'] != 'none' and not item['taxable']:
            description.append(p('VAT exempt', small))
        rows.append([p(index, small), description, p(item['quantity'], right),
                     p(item.get('unit', 'pcs')), p(cash(item['unit_price']), right),
                     p(cash(item['listed_amount']), right)])
    items = Table(rows, colWidths=[28, width - 307, 43, 52, 90, 94],
                  repeatRows=1, hAlign='LEFT', splitInRow=1)
    items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), pale),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), .35, line_color),
        ('LINEBELOW', (0, 0), (-1, -1), .35, line_color),
    ]))
    story += [items, Spacer(1, 13)]

    totals = quote['totals']
    subtotal_label = 'Subtotal (VAT included)' if quote['vat_mode'] == 'inclusive' else 'Subtotal'
    summary = [[p(subtotal_label), p(cash(totals['subtotal']), right)]]
    if Decimal(totals['discount_amount']):
        summary.append([p(f"Discount ({quote['discount']}%)"),
                        p('-' + cash(totals['discount_amount']), right)])
    if quote['vat_mode'] == 'inclusive':
        summary += [[p('Net amount'), p(cash(totals['net']), right)],
                    [p(f"VAT included ({quote['vat_rate']}%)"),
                     p(cash(totals['vat']), right)]]
    elif quote['vat_mode'] == 'exclusive':
        summary.append([p(f"VAT ({quote['vat_rate']}%)"), p(cash(totals['vat']), right)])
    else:
        summary.append([p('VAT'), p('Not applied', right)])
    summary.append([p(f'Total ({currency})', total_label),
                    p(cash(totals['total']), total_right)])
    summary_table = Table(summary, colWidths=[174, 95], hAlign='RIGHT')
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, -1), (-1, -1), .5, line_color),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
    ]))
    story += [KeepTogether([summary_table]), Spacer(1, 18)]
    treatment = {
        'exclusive': 'Unit prices exclude VAT. VAT applies only to taxable items.',
        'inclusive': 'Unit prices include VAT where applicable. The VAT portion is shown above.',
        'none': 'No VAT has been applied to this document.',
    }[quote['vat_mode']]
    story += [p(treatment, small), Spacer(1, 13)]
    for key, title in [('notes', 'Notes'), ('terms', 'Terms and conditions')]:
        if quote.get(key):
            note_heading = p(title, label)
            note_heading.keepWithNext = True
            story += [note_heading, p(quote[key], small), Spacer(1, 9)]

    def page_marks(canvas, doc, continued=False):
        canvas.saveState()
        canvas.setFont(regular, 7)
        canvas.setFillColor(muted)
        if continued:
            canvas.drawString(48, A4[1] - 27, company['name'])
            canvas.drawRightString(A4[0] - 48, A4[1] - 27,
                                  document_title + '  |  ' + quote['number'])
            canvas.setStrokeColor(line_color)
            canvas.setLineWidth(.35)
            canvas.line(48, A4[1] - 34, A4[0] - 48, A4[1] - 34)
        canvas.setStrokeColor(line_color)
        canvas.setLineWidth(.35)
        canvas.line(48, 43, A4[0] - 48, 43)
        canvas.drawString(48, 30, quote['number'] + '  |  ' + company['name'])
        canvas.drawRightString(A4[0] - 48, 30, f'Page {doc.page}')
        canvas.restoreState()

    # Each request writes a separate file before atomically publishing the PDF.
    temporary = output_path.with_name(f'.{output_path.stem}.{uuid4().hex}.pdf.tmp')
    try:
        document = SimpleDocTemplate(
            str(temporary), pagesize=A4, rightMargin=42, leftMargin=42,
            topMargin=44, bottomMargin=62,
            title=f"{document_title} {quote['number']}", author=company['name'])
        document.build(story, onFirstPage=lambda canvas, doc: page_marks(canvas, doc),
                       onLaterPages=lambda canvas, doc: page_marks(canvas, doc, True))
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path
