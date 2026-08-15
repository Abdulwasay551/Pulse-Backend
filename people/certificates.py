import io

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# Matches the app's own brand tokens exactly (frontend/src/app/globals.css
# --primary / --primary-light / --ink / --ink-soft) rather than a guess.
_PRIMARY = HexColor('#ff6b35')
_ACCENT = HexColor('#73b6c4')
_INK = HexColor('#0a2e36')
_INK_SOFT = HexColor('#6d6478')


def render_recognition_certificate(recognition) -> bytes:
    """A simple, honest certificate PDF — no fabricated company seal or
    signature, just the real recognition record (employee, type, who gave
    it, and when)."""
    buffer = io.BytesIO()
    page_size = landscape(letter)
    width, height = page_size
    c = canvas.Canvas(buffer, pagesize=page_size)

    c.setStrokeColor(_PRIMARY)
    c.setLineWidth(3)
    c.rect(0.4 * inch, 0.4 * inch, width - 0.8 * inch, height - 0.8 * inch)
    c.setStrokeColor(_ACCENT)
    c.setLineWidth(1)
    c.rect(0.5 * inch, 0.5 * inch, width - 1.0 * inch, height - 1.0 * inch)

    c.setFillColor(_ACCENT)
    c.setFont('Helvetica', 13)
    c.drawCentredString(width / 2, height - 1.3 * inch, 'Pulse')

    c.setFillColor(_PRIMARY)
    c.setFont('Helvetica-Bold', 32)
    c.drawCentredString(width / 2, height - 2.0 * inch, 'Certificate of Recognition')

    c.setFillColor(_INK_SOFT)
    c.setFont('Helvetica', 14)
    c.drawCentredString(width / 2, height - 2.7 * inch, 'This certificate is proudly presented to')

    c.setFillColor(_INK)
    c.setFont('Helvetica-Bold', 26)
    c.drawCentredString(width / 2, height - 3.4 * inch, recognition.employee.name)

    c.setFillColor(_PRIMARY)
    c.setFont('Helvetica-Bold', 18)
    c.drawCentredString(width / 2, height - 4.1 * inch, recognition.recognition_type)

    if recognition.message:
        c.setFillColor(_INK_SOFT)
        c.setFont('Helvetica-Oblique', 12)
        c.drawCentredString(width / 2, height - 4.6 * inch, f'"{recognition.message}"')

    c.setFillColor(_INK_SOFT)
    c.setFont('Helvetica', 11)
    footer_y = 1.1 * inch
    if recognition.given_by:
        c.drawCentredString(width / 2, footer_y + 0.3 * inch, f'Presented by {recognition.given_by}')
    c.drawCentredString(width / 2, footer_y, recognition.created_at.strftime('%B %d, %Y'))

    c.showPage()
    c.save()
    return buffer.getvalue()
