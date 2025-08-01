import re
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
import re
from PIL import Image
from google import genai
from tavily import TavilyClient
from reportlab.graphics import renderPM
from reportlab.lib.utils import ImageReader
from svglib.svglib import svg2rlg

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_PATH = os.path.join(BASE_DIR, "asset")
tavily = TavilyClient(api_key=os.getenv('TAVILY_API_KEY'))
tavily1 = TavilyClient(api_key=os.getenv('TAVILY_API_KEY1'))
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16)/255 for i in (0, 2, 4))

def draw_name_tag(c, text, x, y, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                  corner_radius=5, font_name="Inter-Bold", font_size=10):
    """
    Draws a name tag rectangle that automatically expands to fit the text.
    - x, y: bottom-left corner of the rectangle.
    """
    # Measure text width
    c.setFont(font_name, font_size)
    text_width = c.stringWidth(text, font_name, font_size)

    # Total width and height with padding
    rect_width = text_width + 2 * padding_x
    rect_height = font_size + 2 * padding_y

    # Draw rounded rectangle
    c.setLineWidth(2)
    c.setStrokeColor(fill_color)
    c.setFillColor(fill_color)
    c.roundRect(x, y, rect_width, rect_height, corner_radius, stroke=1, fill=1)

    # Draw text centered vertically and with horizontal padding
    c.setFillColor(text_color)
    text_x = x + padding_x
    text_y = y + padding_y + 1
    c.drawString(text_x, text_y, text)

def cover_text_generator(pdf, height, ticker, email_text, title_text, company):
    pdf.setFont('Inter-Bold', 40)
    pdf.setFillColor(colors.white)
    pdf.drawString(64,height-582-33,"Intelligence")

    r, g, b = hex_to_rgb("#8B6636")
    pdf.setFillColorRGB(r, g, b)
    pdf.drawString(300,height-582-33,f"Brief")

    if ticker == '' and company == '':
        draw_name_tag(pdf, 'Goliath Obe Tabuni', 64, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
        draw_name_tag(pdf, 'Rueb Vincent', 188, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
    elif ticker != '' and company == '':
        draw_name_tag(pdf, ticker[:4], 64, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
        draw_name_tag(pdf, 'Goliath Obe Tabuni', 124, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
        draw_name_tag(pdf, 'Rueb Vincent', 248, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
    elif ticker == '' and company != '':
        x = 64
        y = height - 646 - 18

        company = company.replace('-', ' ').title()
        for name in [company, 'Goliath Obe Tabuni', 'Rueb Vincent']:
            draw_name_tag(
                pdf, name, x, y,
                padding_x=10, padding_y=6,
                fill_color=colors.white,
                text_color=colors.HexColor("#8B6636"),
                corner_radius=5,
                font_name="Inter", font_size=10
            )
            text_width = pdfmetrics.stringWidth(name, "Inter", 10)
            x += text_width + 2 * 10 + 10  # tag width + spacing
    
    elif ticker != '' and company != '':
        x = 64
        y = height - 646 - 18
        company = company.replace('-', ' ').title()
        for name in [ticker[:4], company, 'Goliath Obe Tabuni', 'Rueb Vincent']:
            draw_name_tag(
                pdf, name, x, y,
                padding_x=10, padding_y=6,
                fill_color=colors.white,
                text_color=colors.HexColor("#8B6636"),
                corner_radius=5,
                font_name="Inter", font_size=10
            )
            text_width = pdfmetrics.stringWidth(name, "Inter", 10)
            x += text_width + 2 * 10 + 10  # tag width + spacing
    
    title_text = title_text.title()
    draw_shrinking_text(pdf, title_text, 400, 64, height-690-15, font_name='Inter-Bold', initial_font_size=20, min_font_size=5, color=colors.white)

    pdf.setFont('Inter', 20)
    pdf.setFillColor(colors.white)
    pdf.drawString(64,height-737-15,"For")

    ## Email

    draw_name_tag(pdf, email_text, 110, height-734-22, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                    corner_radius=5, font_name="Inter", font_size=10)

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

def draw_hyperlink_text(pdf, text, url, max_width, x, y, font_name='Inter-Bold', initial_font_size=30, min_font_size=5, color=colors.white):
    """
    Draws text as a hyperlink at (x, y) with shrinking font size if max_width is exceeded.

    Parameters:
    - pdf: ReportLab canvas object
    - text: The string to draw
    - url: The URL to link to
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

    # Draw the text
    pdf.setFillColor(color)
    pdf.drawString(x, y, text)
    
    # Calculate the actual text width for the link area
    actual_text_width = pdf.stringWidth(text, font_name, font_size)
    pdf.linkURL(url, (x, y, x + actual_text_width, y + font_size))

def draw_justified_hyperlink_text(c, text, url, x, y, max_width, max_height, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2):
    """
    Draws justified hyperlink text within a max width and max height at position (x, y), shrinking font size if needed.
    This function creates clickable links for justified text.

    Parameters:
    - c: ReportLab canvas object
    - text: The text to draw
    - url: The URL to link to
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

    # Draw lines with justification and add hyperlinks
    current_y = y
    for i, line in enumerate(lines):
        line_words = line.split()

        if i == len(lines) - 1 or len(line_words) == 1:
            c.drawString(x, current_y, line)
            # Add hyperlink for the entire line
            line_width = c.stringWidth(line, font_name, font_size)
            c.linkURL(url, (x, current_y, x + line_width, current_y + font_size))
        else:
            total_word_width = sum(c.stringWidth(word, font_name, font_size) for word in line_words)
            space_count = len(line_words) - 1
            if space_count > 0:
                extra_space = (max_width - total_word_width) / space_count
            else:
                extra_space = 0

            word_x = x
            for word in line_words:
                c.drawString(word_x, current_y, word)
                word_x += c.stringWidth(word, font_name, font_size) + extra_space
            
            # Add hyperlink for the entire justified line
            c.linkURL(url, (x, current_y, x + max_width, current_y + font_size))

        current_y -= line_height

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

    ticker_profile = supabase.table("idx_active_company_profile").select("*").eq('symbol', ticker).execute()

    with open(os.path.join(ASSET_PATH,'companiesDesc.json'), 'r') as file:
        data = json.load(file)

    draw_shrinking_text(pdf, ticker_profile.data[0]['company_name'].title(), 500, 51, 725, font_name='Inter-Bold', initial_font_size=30, min_font_size=5, color=colors.white)

    image = ImageReader(BytesIO(requests.get(f"https://storage.googleapis.com/sectorsapp/logo/{ticker[0:4]}.webp").content))
    pdf.drawImage(image, 104, height-188-54, 54, 54, mask="auto")

    website_url = ticker_profile.data[0]['website']
    draw_hyperlink_text(pdf, website_url, website_url, 117, 251, height-217-12, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)

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

def get_company_info_with_tavily(company_name, model='gemini-2.5-flash'):
    # First, search for company information using Tavily
    search_results = tavily1.search(
        query=f"{company_name} Indonesia company or organization information (the name maybe is an abreviation, SEARCH INTENSIVELY IN INDONESIA FIRST. If not found in Indonesia, search in Southeast Asia, then globally.",
        search_depth="advanced",
        include_answer="advanced",
        topic="general",
        include_domains=["linkedin.com", "bloomberg.com", f"{company_name}.com", "idnfinancials.com"],
        max_results=7,
        country="indonesia"
    )
    # print("DEBUG: search_results", search_results)
    # Extract search context from Tavily results
    context = ""
    for img in search_results.get('images', []):
        context += f"Image URL: {img.get('url')}\n"
        context += f"Image Description: {img.get('description')}\n\n"
    for result in search_results.get('results', []):
        context += f"Source: {result.get('url')}\n"
        context += f"Content: {result.get('content')}\n\n"
    
    # Feed the context to the LLM
    prompt = f"""
    Based on the following information about "{company_name}":
    
    {context}
    
    Provide detailed factual information about the company in JSON format.
    If the information about "{company_name}" contains multiple companies or organizations, focus on the one that is most relevant to Indonesia, if not then Southeast Asia.
    
    Include the following fields exactly as listed:
    {{
        "company_name": "Official company name (do not exceed 40 characters because this will be used as a title)",
        "summary": "A comprehensive 2 paragraph (a paragraph contains minimum 4 sentences) summary about description of the company, its business model, key products/services, market position, interesting facts, and so on. MAXIMUM 1300 characters, MINIMUM 900 characters.",
        "website": "Official website URL (should be available and valid, if you cannot find a website, look at the linkedin or crunchbase profile, it usually has a link to the official website)",
        "address": "Headquarters address (if it doesn't available, you can extract 'city, country' or 'country' from summary if there's any)",
        "industry": "Primary industry classification (you can extract this too from the summary if there's no industry data available, but don't imagine things)",
        "sector": "Sector the company operates in (bigger picture than industry, you can extract this too)",
        "inception": "Founding date in YYYY-MM-DD format, if month and day are not available, use only the year (YYYY)",
        "primary_product_service": {{
            "product": "Key product offered by the company (if applicable, otherwise null)",
            "service": "Key service offered by the company (if applicable, otherwise null)"
        }},
        "main_target_market": "Description of the main target market or customer base",
        "social_media": {{
            "linkedin": "LinkedIn profile username",
            "x": "X (formerly Twitter) handle"
        }},
        "ceo_or_key_person": "Name of the CEO or key person in the company (show this field only if this data is available)",
        "interesting_facts": ["create 2-3 interesting facts about the company or organization as a list of strings"],
        "is_company": true/false,
        "sources": [
            "List of URLs (max 5) where this information was obtained"
        ]
    }}

    Only return valid JSON without any explanations or formatting around it.
    If you're unsure about specific information, use null for that field rather than guessing.
    If this doesn't appear to be a company or organization, set is_company to false.
    """
        # "email": "Official contact email address (show this field only if this data is available)",
        # "phone": "Official contact phone number (show this field only if this data is available and only if there's a null value for the website, address, industry, or inception fields)",
    response = client.models.generate_content(model=model, contents=prompt)
    # print("DEBUG: gemini finished")
    return response.text

def extract_company_info(response_text):
    """
    Extract JSON from the response text.
    """
    match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        match = re.search(r"(\{.*\})", response_text, re.DOTALL)
        json_str = match.group(1) if match else None

    if json_str:
        try:
            return json.loads(json_str)
        except Exception as e:
            print(f"JSON parse error: {e}")
            return {}
    return {}

def safe_get(json, key, default='-'):
    value = json.get(key, default)
    if value is None:
        return default
    return value

def get_company_image_with_tavily(links):
    search_results = tavily1.search(
        query=f"From '{links}'. It's about company in Indonesia (or Southeast Asia), provide its official logo URL from the links.",
        search_depth="advanced",
        include_images=True,
        include_image_descriptions=True,
        include_domains=["linkedin.com"],
        max_results=1,
        country="indonesia"
    )
    for img in search_results.get('images', []):
        url = img.get('url', '')
        if 'company-logo' in url:
            return url
    return '-'

def generate_company_page(pdf, height, json):
    # print("DEBUG: json finished")
    # print(json)
    pdf.drawImage(os.path.join(ASSET_PATH, 'company.png'), 0, 0, 595, 842)
    
    company_name = safe_get(json, 'company_name')
    summary = safe_get(json, 'summary')
    summary_len = len(summary) if summary else 0
    summary_height = (summary_len // 95 + 1) * 13 + 20
    website = safe_get(json, 'website')
    address = safe_get(json, 'address')
    industry = safe_get(json, 'industry')
    sector = safe_get(json, 'sector')
    date = safe_get(json, 'inception')
    # email = safe_get(json, 'email')
    social_media = safe_get(json, 'social_media', {})
    # phone = safe_get(json, 'phone')
    ceo_or_key_person = safe_get(json, 'ceo_or_key_person')
    interesting_facts = safe_get(json, 'interesting_facts', {})
    primary_product_service = safe_get(json, 'primary_product_service', {})
    main_target_market = safe_get(json, 'main_target_market')
    sources = safe_get(json, 'sources', [])
    # print("DEBUG: get all data finished")

    if website != '-' or website != 'None':
        source_links = website + ', ' + str(sources)
    elif isinstance(social_media, dict) and social_media.get('linkedin'):
        source_links = 'https://www.linkedin.com/company/' + str(social_media.get('linkedin')) + ', ' + str(sources)
    source_links = source_links[:291]
    
    # print("DEBUG: source_links", source_links)

    logo = get_company_image_with_tavily(source_links)
    # print("DEBUG: logo link ", logo)

    draw_shrinking_text(pdf, company_name, 500, 51, 725, font_name='Inter-Bold', initial_font_size=30, min_font_size=5, color=colors.white)

    # Draw logo if available
    if logo and logo != '-':
        image_url = logo

        try:
            headers = {'User-Agent': 'CompanyReportGenerator/1.0 (contact@example.com)'}
            img_resp = requests.get(image_url, allow_redirects=True, stream=True, timeout=10, headers=headers)
            
            if img_resp.status_code == 200:
                content_type = img_resp.headers.get('Content-Type', '')
                image_content = img_resp.content

                if 'svg' in content_type or logo.lower().endswith('.svg'):
                    # Convert SVG to ReportLab Drawing
                    svg_io = BytesIO(image_content)
                    drawing = svg2rlg(svg_io)

                    # Render drawing to a raster (PNG) image in memory
                    png_io = BytesIO()
                    renderPM.drawToFile(drawing, png_io, fmt='PNG')
                    png_io.seek(0)

                    # Load PNG into reportlab and PIL
                    image = ImageReader(png_io)
                    img_for_size = Image.open(png_io)
                else:
                    image = ImageReader(BytesIO(image_content))
                    img_for_size = Image.open(BytesIO(image_content))

                # Calculate dimensions for the image
                original_width, original_height = img_for_size.size
                max_width = 100
                max_height = 100
                ratio = min(max_width / original_width, max_height / original_height)
                new_width = original_width * ratio
                new_height = original_height * ratio
                x_pos = 100 + (max_width - new_width) / 2
                y_pos = (height - 248 - 54) + (max_height - new_height) / 2

                pdf.drawImage(image, x_pos, y_pos, new_width, new_height, mask="auto")

        except Exception as e:
            print(f"The image cannot be loaded: {e}")
    else:
        # Draw periwatch logo if company logo isn't available
        img_path = os.path.join(ASSET_PATH, 'periwatch.png')
        if os.path.exists(img_path):
            image = ImageReader(img_path)
            img_for_size = Image.open(img_path)
            original_width, original_height = img_for_size.size
            max_width = 90
            max_height = 90
            ratio = min(max_width / original_width, max_height / original_height)
            new_width = original_width * ratio
            new_height = original_height * ratio
            x_pos = 105 + (max_width - new_width) / 2
            y_pos = (height - 242 - 54) + (max_height - new_height) / 2

            pdf.drawImage(image, x_pos, y_pos, new_width, new_height, mask="auto")

    # Website
    if website != 'None' and website != '-':
        draw_shrinking_text(pdf, 'WEBSITE', 117, 251, height-200-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
        draw_hyperlink_text(pdf, website, website, 117, 251, height-217-12+2, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)
    else:
        social_text = '-'
        social_url = '-'
        if isinstance(social_media, dict):
            if social_media.get('linkedin'):
                social_text = f"{social_media['linkedin']}"
                social_url = f"https://www.linkedin.com/company/{social_media['linkedin']}"
                draw_shrinking_text(pdf, 'LINKEDIN', 117, 251, height-200-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
            elif social_media.get('x'):
                social_text = f"{social_media['x']}"
                social_url = f"https://twitter.com/{social_media['x']}"
                draw_shrinking_text(pdf, 'X', 117, 251, height-200-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
        
        if social_url != '-':
            draw_hyperlink_text(pdf, social_text, social_url, 117, 251, height-217-12+2, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)
        else:
            draw_shrinking_text(pdf, social_text, 117, 251, height-217-12+2, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)

    # Address
    draw_justified_text(pdf, 'ADDRESS', 251, height-269-12+2, 117, 36, font_name="Inter", initial_font_size=10, min_font_size=5, line_spacing=2)
    draw_justified_text(pdf, address.title(), 251, height-286-12+2, 117, 30, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)

    # Industry
    if industry and industry != '-':
        draw_shrinking_text(pdf, 'INDUSTRY', 117, 401, height-200-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
        draw_justified_text(pdf, industry.title(), 401, height-217-12+2, 117, 30, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)
    else:
        draw_shrinking_text(pdf, 'SECTOR', 117, 401, height-200-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
        draw_justified_text(pdf, sector.title(), 401, height-217-12+2, 117, 30, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)

    # Inception Date, with fallback
    if date and date != '-':
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            date_str = dt.strftime('%d %B %Y').title()
        except Exception:
            date_str = date
        draw_shrinking_text(pdf, 'ESTABLISHED', 117, 401, height-269-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
        pdf.drawString(401, height-286-12+2, date_str)
    elif ceo_or_key_person and ceo_or_key_person != '-':
        draw_shrinking_text(pdf, 'KEY PERSON', 117, 401, height-269-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
        draw_shrinking_text(pdf, ceo_or_key_person, 117, 401, height-286-12+2, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)
    elif primary_product_service and isinstance(primary_product_service, dict):
        product = primary_product_service.get('product')
        service = primary_product_service.get('service')
        if product and product != '-':
            draw_shrinking_text(pdf, 'PRIMARY PRODUCT', 117, 401, height-269-12+2, font_name='Inter', initial_font_size=10, min_font_size=10, color=colors.white)
            draw_justified_text(pdf, product, 401, height-286-12+2, 117, 30, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)
        elif service and service != '-':
            draw_shrinking_text(pdf, 'PRIMARY SERVICE', 117, 401, height-269-12+2, font_name='Inter', initial_font_size=10, min_font_size=10, color=colors.white)
            draw_justified_text(pdf, service, 401, height-286-12+2, 117, 30, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)
    elif main_target_market and main_target_market != '-':
        draw_shrinking_text(pdf, 'TARGET MARKET', 117, 401, height-269-12+2, font_name='Inter', initial_font_size=10, min_font_size=5, color=colors.white)
        draw_justified_text(pdf, main_target_market, 401, height-286-12+2, 117, 30, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)
    
    # Company brief description
    draw_justified_text(pdf, summary, 64, height-391-12, 464, 140, font_name="Inter", initial_font_size=14, min_font_size=10, line_spacing=2)

    # Company Interesting Facts
    if interesting_facts and isinstance(interesting_facts, list):
        pdf.setFont('Inter-Bold', 14)
        pdf.drawString(64, height-391-12 - summary_height, "Key Details")
        
        y_position = height - 411 - 12 - summary_height
        
        facts = interesting_facts

        for fact in facts:
            if not fact:
                continue
            
            # Add bullet point
            bullet_point = "•"
            
            # Set font for bullet point and text
            pdf.setFont("Inter", 10)
            
            # Calculate text width to wrap it
            max_width = 464
            lines = []
            words = fact.split()
            current_line = ""
            
            for word in words:
                test_line = f"{current_line} {word}".strip()
                if pdf.stringWidth(test_line, "Inter", 10) <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            lines.append(current_line)
            
            # Draw the lines
            for i, line in enumerate(lines):
                if i == 0:
                    pdf.drawString(64, y_position, bullet_point)
                    pdf.drawString(74, y_position, line)
                else:
                    pdf.drawString(74, y_position, line)
                y_position -= 12  # Move to the next line
            
            y_position -= 6 # Add extra space between facts

def generate_pdf(title_text, email_text, ticker, company):
    buffer = BytesIO()
    width, height = 595, 842

    pdfmetrics.registerFont(TTFont('Inter', os.path.join(ASSET_PATH, "font/Inter-Regular.ttf")))
    pdfmetrics.registerFont(TTFont('Inter-Bold', os.path.join(ASSET_PATH, "font/Inter-Bold.ttf")))
    pdf = canvas.Canvas(buffer, pagesize=(width, height))

    # Cover Page
    pdf.drawImage(os.path.join(ASSET_PATH,'cover.png'), 0, 0, width, height)
    
    if company != '':
        cover_text_generator(pdf, height, ticker, email_text, title_text, company)
    else:
        cover_text_generator(pdf, height, ticker, email_text, title_text, '')
    pdf.showPage()

    # Ticker page
    if ticker != '':
        pdf.drawImage(f'api/asset/ticker.png', 0, 0, width, height)
        generate_ticker_page(pdf, ticker, height)
        pdf.showPage()

    if company != '':
        generate_company_page(pdf, 842, extract_company_info(get_company_info_with_tavily(company)))
        # json_dummy = {'company_name': 'The Audit Board of Indonesia (BPK RI)', 'summary': "The Audit Board of Indonesia (BPK RI) is a prominent government administration body responsible for independently auditing state financial management and accountability. Its core mission is to implement good governance by upholding integrity, independence, and professionalism in its operations. The organization specializes in crucial areas such as audit, investigation, finance, government, and performance evaluations, playing a vital role in ensuring transparency and accountability in national financial affairs. BPK RI acts as a critical oversight mechanism for public funds.\n\nFounded in 1947, BPK RI has established itself as a cornerstone of Indonesia's financial governance, aiming to be a driving force in state financial management to achieve national goals through high-quality and value-added audits. With a significant workforce of over 10,001 employees, it is one of the largest government bodies in Indonesia, demonstrating its extensive reach and impact. The institution's commitment to its vision ensures that state financial practices are scrutinized to foster national development and uphold public trust. Its influence extends across all levels of government finance.", 'website': None, 'address': 'Jakarta Pusat, DKI Jakarta', 'industry': 'Government Administration', 'sector': 'Government', 'inception': '1947', 'primary_product_service': {'product': None, 'service': 'Audit, Investigation, Financial Oversight'}, 'main_target_market': 'Indonesian government entities and public financial management', 'social_media': {'linkedin': 'the-audit-board-of-indonesia-bpk-ri-', 'x': None}, 'ceo_or_key_person': None, 'interesting_facts': ['It is the supreme audit institution of Indonesia, responsible for auditing the financial management of the state.', 'Established in 1947, BPK RI has a long-standing history that predates the formal independence of many modern nations, highlighting its foundational role in Indonesian governance.', 'Its core values of integrity, independence, and professionalism are explicitly stated as integral to its mission, ensuring unbiased financial oversight.'], 'is_company': False, 'sources': ['https://ca.linkedin.com/company/the-audit-board-of-indonesia-bpk-ri-?trk=public_profile_experience-item_profile-section-card_subtitle-click', 'https://si.linkedin.com/company/the-audit-board-of-indonesia-bpk-ri-', 'https://za.linkedin.com/company/the-audit-board-of-indonesia-bpk-ri-?trk=similar-pages_result-card_full-click']}
        # generate_company_page(pdf, 842, json_dummy)
        pdf.showPage()

    # Page 1
    pdf.drawImage(os.path.join(ASSET_PATH,'goliath.png'), 0, 0, width, height)
    pdf.showPage()

    # Page 2
    pdf.drawImage(os.path.join(ASSET_PATH,'vincent.png'), 0, 0, width, height)
    pdf.showPage()

    # CTA
    pdf.drawImage(os.path.join(ASSET_PATH,'cta.png'), 0, 0, width, height)
    pdf.showPage()

    pdf.save()
    buffer.seek(0)
    return buffer