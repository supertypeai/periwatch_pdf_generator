from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from io import BytesIO
import os
import json
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime
from reportlab.lib.utils import ImageReader
import requests

load_dotenv()

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

def draw_shrinking_text(pdf, text, max_width, x, y, font_name='Inter-Bold', initial_font_size=30, min_font_size=5, color=colors.white):
    """
    Draws text at (x, y) with shrinking font size if max_width is exceeded.

    Parameters:
    - pdf: ReportLab canvas object
    - text: The string to draw
    - max_width: Maximum allowed width for the text
    - x, y: Coordinates to draw the text
    - font_name: Font to use (default: 'Inter-Bold')
    - initial_font_size: Starting font size (default: 30)
    - min_font_size: Minimum font size allowed (default: 5)
    - color: Text color (default: white)
    """
    font_size = initial_font_size
    pdf.setFont(font_name, font_size)
    text_width = pdf.stringWidth(text, font_name, font_size)

    while text_width > max_width and font_size > min_font_size:
        font_size -= 1
        pdf.setFont(font_name, font_size)
        text_width = pdf.stringWidth(text, font_name, font_size)

    pdf.setFillColor(color)
    pdf.drawString(x, y, text)

def draw_justified_text(c, text, x, y, max_width, max_height, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2):
    """
    Draws justified text within a max width and max height at position (x, y), shrinking font size if needed.

    Parameters:
    - c: ReportLab canvas object
    - text: The text to draw
    - x, y: Starting coordinates
    - max_width: Maximum allowed width for text lines
    - max_height: Maximum allowed height for all lines combined
    - font_name: Font to use
    - initial_font_size: Starting font size
    - min_font_size: Minimum font size allowed
    - line_spacing: Additional space between lines
    """
    font_size = initial_font_size

    while font_size >= min_font_size:
        c.setFont(font_name, font_size)
        words = text.split()
        line = ""
        lines = []

        # Split text into lines based on max_width
        for word in words:
            test_line = f"{line} {word}".strip()
            if c.stringWidth(test_line, font_name, font_size) <= max_width:
                line = test_line
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)

        line_height = font_size + line_spacing
        total_height = line_height * len(lines)

        # Check if total height fits within max_height
        if total_height <= max_height:
            break
        else:
            font_size -= 1  # Shrink font and try again

    # Draw lines with justification
    for i, line in enumerate(lines):
        line_words = line.split()

        if i == len(lines) - 1 or len(line_words) == 1:
            c.drawString(x, y, line)
        else:
            total_word_width = sum(c.stringWidth(word, font_name, font_size) for word in line_words)
            space_count = len(line_words) - 1
            if space_count > 0:
                extra_space = (max_width - total_word_width) / space_count
            else:
                extra_space = 0

            word_x = x
            for word in line_words:
                c.drawString(word_x, y, word)
                word_x += c.stringWidth(word, font_name, font_size) + extra_space

        y -= line_height

def generate_ticker_page(pdf, ticker, height):
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)

    ticker_profile = supabase.table("idx_active_company_profile").select("*").eq('symbol',ticker).execute()

    with open(os.path.join(ASSET_PATH,'companiesDesc.json'), 'r') as file:
        data = json.load(file)

    draw_shrinking_text(pdf, ticker_profile.data[0]['company_name'].title(), 500, 51, 725, font_name='Inter-Bold', initial_font_size=30, min_font_size=5, color=colors.white)

    image = ImageReader(BytesIO(requests.get(f"https://storage.googleapis.com/sectorsapp/logo/{ticker[0:4]}.webp").content))
    pdf.drawImage(image, 104, height-188-54, 54, 54, mask="auto")

    draw_shrinking_text(pdf, ticker_profile.data[0]['website'], 117, 251, height-217-12, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)

    pdf.setFont('Inter-Bold', 10)
    pdf.drawString(401, height-217-12, ticker_profile.data[0]['phone'])

    draw_justified_text(pdf, ticker_profile.data[0]['address'], 72, height-286-12, 147, 36, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)

    draw_shrinking_text(pdf, ticker_profile.data[0]['industry'].title(), 117, 251, height-286-12, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)

    pdf.drawString(401, height-286-12, datetime.strptime(ticker_profile.data[0]['listing_date'], '%Y-%m-%d').strftime('%d %B %Y').title())

    draw_justified_text(pdf, data[ticker], 64, height-396-12, 464, 140, font_name="Inter", initial_font_size=14, min_font_size=5, line_spacing=2)

    pdf.setFont('Inter-Bold', 10)
    pdf.drawString(64, height-611-12, "Major Shareholders")
    draw_justified_text(pdf, ', '.join(f"{s['name']} ({s['share_percentage']*100:.2f}%)" for s in ticker_profile.data[0]['shareholders']), 191, height-611-12, 348, 45, font_name="Inter", initial_font_size=10, min_font_size=5, line_spacing=2)

    pdf.setFont('Inter-Bold', 10)
    pdf.drawString(64, height-668-12, "Directors")
    draw_justified_text(pdf, ', '.join(f"{s['name']} ({s['position']})" for s in ticker_profile.data[0]['directors']), 191, height-668-12, 348, 45, font_name="Inter", initial_font_size=10, min_font_size=5, line_spacing=2)

    pdf.setFont('Inter-Bold', 10)
    pdf.drawString(64, height-725-12, "Commissioner")
    draw_justified_text(pdf, ', '.join(f"{s['name']} ({s['position']})" for s in ticker_profile.data[0]['comissioners']), 191, height-725-12, 348, 45, font_name="Inter", initial_font_size=10, min_font_size=5, line_spacing=2)

def generate_pdf(title_text, email_text, ticker):
    buffer = BytesIO()
    width, height = 595, 842

    pdfmetrics.registerFont(TTFont('Inter', os.path.join(ASSET_PATH, "font/Inter-Regular.ttf")))
    pdfmetrics.registerFont(TTFont('Inter-Bold', os.path.join(ASSET_PATH, "font/Inter-Bold.ttf")))
    pdf = canvas.Canvas(buffer, pagesize=(width, height))

    # Cover Page
    pdf.drawImage(os.path.join(ASSET_PATH,'cover.png'), 0, 0, width, height)
    
    if ticker == "":
        title_text_generator(pdf, title_text)
        email_text_generator(pdf, email_text)
    else:
        pdf.setFont('Inter-Bold', 32)
        pdf.setFillColor(colors.white)
        pdf.drawString(70,158,"Intelligence Brief")

        r, g, b = hex_to_rgb("#8B6636")
        pdf.setFillColorRGB(r, g, b)
        pdf.drawString(345,158,f"of {ticker}")
        email_text_generator(pdf, email_text)

    # Ticker Page
        pdf.showPage()
        pdf.drawImage(os.path.join(ASSET_PATH,'ticker.png'), 0, 0, width, height)
        generate_ticker_page(pdf, ticker, height)    

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
