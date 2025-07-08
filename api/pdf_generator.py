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
import wikipediaapi
import wptools
import re
import requests
from spellchecker import SpellChecker
import cairosvg
from PIL import Image
import unicodedata

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_PATH = os.path.join(BASE_DIR, "asset")

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

def cover_text_generator(pdf,height,ticker,email_text,title_text):
    pdf.setFont('Inter-Bold', 40)
    pdf.setFillColor(colors.white)
    pdf.drawString(64,height-582-33,"Intelligence")

    r, g, b = hex_to_rgb("#8B6636")
    pdf.setFillColorRGB(r, g, b)
    pdf.drawString(300,height-582-33,f"Brief")

    if ticker == '':
        draw_name_tag(pdf, 'Goliath Obe Tabuni', 64, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
        draw_name_tag(pdf, 'Rueb Vincent', 188, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
    else:
        draw_name_tag(pdf, ticker[:4], 64, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
        draw_name_tag(pdf, 'Goliath Obe Tabuni', 124, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)
        draw_name_tag(pdf, 'Rueb Vincent', 248, height-646-18, padding_x=10, padding_y=6, fill_color=colors.white, text_color=colors.HexColor("#8B6636"),
                        corner_radius=5, font_name="Inter", font_size=10)

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

def clean_wiki_value(value):
    if not value or value == '-':
        return '-'
    url_match = re.match(r'\{\{URL\|(.*?)\}\}', value)
    if url_match:
        return url_match.group(1)
    value = re.sub(r'\[\[(.*?)\]\]', lambda m: m.group(1).split('|')[-1], value)
    value = re.sub(r'\{\{.*?\}\}', '', value)
    value = value.replace('[', '').replace(']', '').replace('|', ',')
    return value.strip()

def get_wikidata_label(qid, lang='en'):
    if not qid or not isinstance(qid, str) or not qid.startswith('Q'):
        return qid
    url = f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json'
    try:
        resp = requests.get(url)
        data = resp.json()
        entity = data['entities'][qid]
        return entity['labels'][lang]['value']
    except Exception:
        return qid

def get_wikidata_info(wikibase_id):
    url = f'https://www.wikidata.org/wiki/Special:EntityData/{wikibase_id}.json'
    resp = requests.get(url)
    data = resp.json()
    entity = data['entities'][wikibase_id]
    claims = entity['claims']

    def get_value(prop, resolve_label=False):
        if prop in claims:
            mainsnak = claims[prop][0]['mainsnak']
            datavalue = mainsnak.get('datavalue', {})
            value = datavalue.get('value')
            if isinstance(value, dict):
                if 'text' in value:
                    return value['text']
                elif 'id' in value and resolve_label:
                    return get_wikidata_label(value['id'])
                elif 'time' in value:
                    date_str = value['time']
                    return date_str[1:11]
            elif isinstance(value, str):
                return value
        return '-'

    website = get_value('P856')
    industry = get_value('P452', resolve_label=True)
    official_name = get_value('P1448')
    logo = get_value('P154')
    address = get_value('P6375')
    inception = get_value('P571', resolve_label=True)
    if not address or address == '-':
        address = get_value('P159', resolve_label=True)

    return {'website': website, 'industry': industry, 'official_name': official_name, 'logo': logo, 'address': address, 'inception': inception}

def try_wikipedia_variants(company_name):
    wiki = wikipediaapi.Wikipedia(user_agent="periwatch_pdf_generator/1.0", language='en', extract_format=wikipediaapi.ExtractFormat.WIKI)
    variants = [
        company_name
        # company_name.title(),
        # company_name.lower(),
        # company_name.upper()
    ]
    for name in variants:
        page = wiki.page(name)
        if page.exists():
            return page, name
    # If not found, try Wikipedia search suggest
    suggested = wikipedia_search_suggest(company_name)
    if suggested:
        page = wiki.page(suggested)
        if page.exists():
            return page, suggested
    return None, company_name

def try_wptools_variants(company_name):
    variants = [
        company_name
        # company_name.title(),
        # company_name.lower(),
        # company_name.upper()
    ]
    for name in variants:
        page = wptools.page(name, lang='en')
        try:
            page.get_parse()
            if page.data.get('wikibase'):
                return page, name
        except Exception:
            continue
    # If not found, try Wikipedia search suggest
    suggested = wikipedia_search_suggest(company_name)
    if suggested:
        page = wptools.page(suggested, lang='en')
        try:
            page.get_parse()
            if page.data.get('wikibase'):
                return page, suggested
        except Exception:
            pass
    return None, company_name

def wikipedia_search_suggest_list(query, limit=5):
    """Returns a list of Wikipedia search suggestions."""
    url = 'https://en.wikipedia.org/w/api.php'
    params = {
        'action': 'opensearch',
        'search': query,
        'limit': limit,
        'namespace': 0,
        'format': 'json'
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()  # Raise an exception for bad status codes
        data = resp.json()
        if data and len(data) > 1 and data[1]:
            # Return the whole list of suggestions
            return data[1]
    except Exception as e:
        print(f"API request failed: {e}")
    # Return an empty list if anything goes wrong
    return []

def wikipedia_search_suggest(query):
    url = f'https://en.wikipedia.org/w/api.php'
    params = {
        'action': 'opensearch',
        'search': query,
        'limit': 1,
        'namespace': 0,
        'format': 'json'
    }
    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        if data and len(data) > 1 and data[1]:
            return data[1][0]
    except Exception:
        pass
    return None

def is_company_wikidata(wikibase_id):
    """Return True if the Wikidata entity is a company/organization."""
    company_qids = {
        "Q783794",      # enterprise
        "Q43229",       # state-owned enterprise (BUMN)
        "Q6881511",     # corporation
        "Q167037",      # public company
        "Q4830453",     # business
        "Q891723",      # subsidiary
        "Q1370346",     # private company
        "Q2221906",     # holding company
        "Q15911313",    # limited liability company
        "Q161604",      # cooperative
        "Q1921501",     # sole proprietorship (usaha perorangan)
        "Q159433",      # partnership
        "Q163740",      # non-profit organization
        "Q1058914",     # software company
        "Q1055701",     # computer manufacturing company
    }
    url = f'https://www.wikidata.org/wiki/Special:EntityData/{wikibase_id}.json'
    try:
        resp = requests.get(url)
        data = resp.json()
        entity = data['entities'][wikibase_id]
        claims = entity.get('claims', {})
        if 'P31' in claims:
            for claim in claims['P31']:
                mainsnak = claim.get('mainsnak', {})
                datavalue = mainsnak.get('datavalue', {})
                value = datavalue.get('value', {})
                if isinstance(value, dict) and value.get('id') in company_qids:
                    print(f"Wikidata entity {wikibase_id} is a company.")
                    return True
            print(f"Wikidata entity {wikibase_id} is not a company.")
        return False
    except Exception:
        return False
    
def smart_query(query):
    """
    Enhanced function to clean and correct a query before searching Wikipedia.
    """
    if not query or not isinstance(query, str):
        return None
    spell = SpellChecker(language='en')
    delete_text = ['pt', 'cv', 'tbk', 'persero', 'inc', 'corp', 'ltd']
    words = query.lower().split()
    
    # Step 1: Delete unwanted prefixes
    clean_words = [word for word in words if word not in delete_text]
    clean_query = ' '.join(clean_words)

    to_be_corrected = clean_query.split()
    miss_spelled = spell.unknown(to_be_corrected)
    
    # Step 2: Correct spelling errors
    final_words = []
    for word in to_be_corrected:
        if word in miss_spelled:
            correction = spell.correction(word)
            final_words.append(correction if correction is not None else word)
        else:
            final_words.append(word)
            
    query_final = ' '.join(final_words)
    
    print(f"Input asli: '{query}' -> Query setelah dibersihkan & dikoreksi: '{query_final}'")
    return query_final
    # suggest = wikipedia_search_suggest(query_final)
    # if not suggest:
    #     suggest = wikipedia_search_suggest(clean_query)
    # if not suggest:
    #     suggest = wikipedia_search_suggest(query)
    # return suggest

def get_corrected_wikidata_id(company_name):
    # Try Wikipedia and Wikidata with several case variants
    company_name = wikipedia_search_suggest(company_name)
    page_py, used_name = try_wikipedia_variants(company_name)
    page, _ = try_wptools_variants(company_name)
    summary = page_py.summary if page_py else ''
    wikibase_id = page.data.get('wikibase') if page else None
    if is_company_wikidata(wikibase_id) and summary != '':
        return wikibase_id, company_name, summary
    company_name = smart_query(company_name)
    page_py, used_name = try_wikipedia_variants(company_name)
    page, _ = try_wptools_variants(company_name)
    summary = page_py.summary if page_py else ''
    wikibase_id = page.data.get('wikibase') if page else None
    return wikibase_id, used_name, summary

def find_company_page(company_name):
    """
    Searches for a company on Wikipedia and returns its validated Wikidata ID,
    page title, and summary. It ensures the found page corresponds to a company entity.
    """
    # Use your smart_query to clean the initial name
    cleaned_name = smart_query(company_name) or company_name
    
    # Create a list of queries to try, from most to least specific
    search_queries = [
        cleaned_name,
        company_name,
        f"{cleaned_name} (company)",
        f"{cleaned_name} Corporation"
    ]

    # Keep track of pages we've already checked to avoid redundant API calls
    checked_pages = set()

    for query in search_queries:
        suggestions = wikipedia_search_suggest_list(query)
        for suggestion in suggestions:
            if suggestion in checked_pages:
                continue
            checked_pages.add(suggestion)

            print(f"Validating suggestion: '{suggestion}'...")
            try:
                # Use wptools to get the wikibase_id
                page = wptools.page(suggestion, lang='en', silent=True)
                page.get_parse()
                wikibase_id = page.data.get('wikibase')

                if wikibase_id:
                    # Validate if the wikidata entity is a company
                    if is_company_wikidata(wikibase_id):
                        # Use wikipedia-api to get a clean summary
                        wiki_api = wikipediaapi.Wikipedia(user_agent="Periwatch/1.0", language='en')
                        page_py = wiki_api.page(suggestion)
                        
                        if page_py.exists():
                            return wikibase_id, suggestion, page_py.summary
            except Exception:
                # Ignore errors from suggestions that don't lead to a valid page
                continue
    
    return None, company_name, ""

def generate_company_page(pdf, wikibase_id, height, used_name, summary):
    pdf.drawImage(os.path.join(ASSET_PATH, 'company.png'), 0, 0, 595, 842)
    
    wikidata = get_wikidata_info(wikibase_id) if wikibase_id else {}
    website = wikidata.get('website', '-')
    address = wikidata.get('address', '-')
    industry = wikidata.get('industry', '-')
    logo = wikidata.get('logo', None)
    official_name = wikidata.get('official_name', '-')
    date = wikidata.get('inception', '-')

    if contains_non_ascii(official_name) or official_name == '-':
        draw_shrinking_text(pdf, used_name, 500, 51, 725, font_name='Inter-Bold', initial_font_size=30, min_font_size=5, color=colors.white)
    else:
        draw_shrinking_text(pdf, official_name, 500, 51, 725, font_name='Inter-Bold', initial_font_size=30, min_font_size=5, color=colors.white)

    # Draw logo if available
    if logo and logo != '-':
        image_url = f'https://commons.wikimedia.org/wiki/Special:FilePath/{logo.replace(" ", "_")}' # Ganti spasi dengan underscore

        try:
            headers = {'User-Agent': 'CompanyReportGenerator/1.0 (contact@example.com)'}
            img_resp = requests.get(image_url, allow_redirects=True, stream=True, timeout=10, headers=headers)
            
            if img_resp.status_code == 200:
                content_type = img_resp.headers.get('Content-Type', '')
                image_content = img_resp.content
                final_image_bytes = None
                # Convert SVG to PNG if necessary
                if 'svg' in content_type or logo.lower().endswith('.svg'):
                    png_bytes = cairosvg.svg2png(bytestring=image_content)
                    image = ImageReader(BytesIO(png_bytes))
                    img_for_size = Image.open(BytesIO(png_bytes))
                else:
                    image = ImageReader(BytesIO(image_content))
                    img_for_size = Image.open(BytesIO(image_content))

                # Ambil ukuran asli gambar
                original_width, original_height = img_for_size.size
                max_width = 120
                max_height = 120
                ratio = min(max_width / original_width, max_height / original_height)
                new_width = original_width * ratio
                new_height = original_height * ratio
                x_pos = 90 + (max_width - new_width) / 2
                y_pos = (height - 248 - 54) + (max_height - new_height) / 2

                pdf.drawImage(image, x_pos, y_pos, new_width, new_height, mask="auto")

        except Exception as e:
            print(f"🔥 Terjadi kesalahan tak terduga saat memproses gambar: {e}")

    # Website
    draw_shrinking_text(pdf, website if website != '-' else '', 117, 251, height-217-12, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)

    # Address
    draw_justified_text(pdf, address if address != '-' else '', 251, height-286-12, 147, 36, font_name="Inter-Bold", initial_font_size=10, min_font_size=5, line_spacing=2)

    # Industry
    draw_shrinking_text(pdf, industry.title() if industry != '-' else '', 117, 401, height-217-12, font_name='Inter-Bold', initial_font_size=10, min_font_size=5, color=colors.white)

    # Listing date (pakai inception)
    if date and date != '-':
        try:
            # Jika date sudah format YYYY-MM-DD
            dt = datetime.strptime(date, '%Y-%m-%d')
            date_str = dt.strftime('%d %B %Y').title()
        except Exception:
            date_str = date
        pdf.drawString(401, height-286-12, date_str)
    else:
        pdf.drawString(401, height-286-12, "")

    # Company brief description
    draw_justified_text(pdf, summary, 64, height-396-12, 464, 140, font_name="Inter", initial_font_size=14, min_font_size=10, line_spacing=2)

def generate_pdf(title_text, email_text, ticker, company):
    buffer = BytesIO()
    width, height = 595, 842

    pdfmetrics.registerFont(TTFont('Inter', os.path.join(ASSET_PATH, "font/Inter-Regular.ttf")))
    pdfmetrics.registerFont(TTFont('Inter-Bold', os.path.join(ASSET_PATH, "font/Inter-Bold.ttf")))
    pdf = canvas.Canvas(buffer, pagesize=(width, height))

    # Cover Page
    pdf.drawImage(os.path.join(ASSET_PATH,'cover.png'), 0, 0, width, height)
    cover_text_generator(pdf, height, company, email_text, title_text)
    pdf.showPage()

    # Ticker page
    if ticker != '':
        pdf.drawImage(f'api/asset/ticker.png', 0, 0, width, height)
        generate_ticker_page(pdf, ticker, height)
        pdf.showPage()

    if company != '':
        wikibase_id, used_name, summary = find_company_page(company)
        if wikibase_id:
            generate_company_page(pdf, wikibase_id, 842, used_name, summary)
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

def contains_non_ascii(text):
    for char in text:
        code = ord(char)
        if (0x4E00 <= code <= 0x9FFF) or \
            (0xAC00 <= code <= 0xD7A3) or \
            (0x3040 <= code <= 0x309F) or \
            (0x30A0 <= code <= 0x30FF):
            return True
        category = unicodedata.category(char)
        if category.startswith('C'):
            return True
    return False