from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from io import BytesIO
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_PATH = os.path.join(BASE_DIR, "asset")

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16)/255 for i in (0, 2, 4))

def email_text_generator(pdf, email_text):
    max_width = 326
    font_name = "Inter"
    font_size = 16
    min_font_size = 5

    while font_size >= min_font_size:
        text_width = pdfmetrics.stringWidth(email_text, font_name, font_size)
        if text_width <= max_width:
            break
        font_size -= 1

    pdf.setFont(font_name, font_size)
    r, g, b = hex_to_rgb("#8B6636")
    pdf.setFillColorRGB(r, g, b)
    pdf.drawString(132, 100, email_text)

def title_text_generator(pdf, text):
    x = 70
    y = 158
    max_width = 483
    font_name = "Inter-Bold"
    font_size = 40

    words = text.split()
    visible_words = []
    current_width = 0

    ellipsis_width = pdfmetrics.stringWidth("...", font_name, font_size)

    for word in words:
        word_to_add = word + " "
        word_width = pdfmetrics.stringWidth(word_to_add, font_name, font_size)
        
        if current_width + word_width + ellipsis_width <= max_width:
            visible_words.append(word)
            current_width += word_width
        else:
            break

    truncated = len(visible_words) < len(words)
    visible_text = " ".join(visible_words)
    if truncated:
        visible_text += "..."

    visible_words_split = visible_text.split()
    half_index = len(visible_words_split) // 2
    first_part = " ".join(visible_words_split[:half_index])
    second_part = " ".join(visible_words_split[half_index:])

    first_width = pdfmetrics.stringWidth(first_part.upper(), font_name, font_size)

    pdf.setFont(font_name, font_size)
    pdf.setFillColor(colors.white)
    pdf.drawString(x, y, first_part.upper())

    r, g, b = hex_to_rgb("#8B6636")
    pdf.setFillColorRGB(r, g, b)
    pdf.drawString(x + first_width, y, f" {second_part.upper()}")

def generate_pdf(title_text, email_text):
    buffer = BytesIO()
    width, height = 595, 842

    pdfmetrics.registerFont(TTFont('Inter', os.path.join(ASSET_PATH, "font/Inter-Regular.ttf")))
    pdfmetrics.registerFont(TTFont('Inter-Bold', os.path.join(ASSET_PATH, "font/Inter-Bold.ttf")))
    pdf = canvas.Canvas(buffer, pagesize=(width, height))

    # Cover Page
    pdf.drawImage(os.path.join(ASSET_PATH,'cover.png'), 0, 0, width, height)
    title_text_generator(pdf, title_text)
    email_text_generator(pdf, email_text)

    # Page 1
    pdf.showPage()
    pdf.drawImage(os.path.join(ASSET_PATH,'goliath.png'), 0, 0, width, height)

    # Page 2
    pdf.showPage()
    pdf.drawImage(os.path.join(ASSET_PATH,'vincent.png'), 0, 0, width, height)

    # CTA
    pdf.showPage()
    pdf.drawImage(os.path.join(ASSET_PATH,'cta.png'), 0, 0, width, height)

    pdf.save()
    buffer.seek(0)
    return buffer
