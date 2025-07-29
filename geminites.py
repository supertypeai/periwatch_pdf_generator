from google import genai
from tavily import TavilyClient
import os
import dotenv
import re
import json

dotenv.load_dotenv()

tavily = TavilyClient(api_key=os.getenv('TAVILY_API_KEY'))

def get_company_info_with_tavily(company_name, model='gemini-2.5-flash'):
    # First, search for company information using Tavily
    search_results = tavily.search(
        query=f"{company_name} Indonesia company or organization information (the name maybe is an abreviation, SEARCH INTENSIVELY IN INDONESIA FIRST. If not found in Indonesia, search in Southeast Asia. If still not found, search globally. Images URL that you generate will be a logo, not something else. If it isn't a logo, don't include it on the result)",
        search_depth="advanced",
        include_images=True,
        include_image_descriptions=True,
        topic="general",
        include_domains=["linkedin.com", "crunchbase.com", "bloomberg.com", "reuters.com", "idnfinancials.com"],
        max_results=7,
        country="indonesia"
    )
    
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
        "summary": "A comprehensive 2-3 paragraph (a paragraph contains minimum 4 sentences) about description of the company, its business model, key products/services, market position, interesting facts, and so on",
        "logo": "Image logo URL that is the most suitable by the description, only choose one URL. Do not choose the logo that not match the summary and company name",
        "website": "Official website URL (should be available and valid, if you cannot find a website, look at the linkedin or crunchbase profile, it usually has a link to the official website)",
        "address": "Headquarters address (if it doesn't available, you can extract 'city, country' from summary if there's any)",
        "industry": "Primary industry classification",
        "sector": "Sector the company operates in (only show this if industry data is null, then don't show the industry field)",
        "inception": "Founding date in YYYY-MM-DD format, if month and day are not available, use only the year (YYYY)",
        "email": "Official contact email address (show this field only if this data is available and only if there's a null value for the website, address, industry, or inception fields)",
        "social_media": {{(chose one of the following based on the context provided)
            "linkedin": "LinkedIn profile username",
            "x": "X (formerly Twitter) handle"
            (show this field only if this data is available and only if there's a null value for the website, address, industry, or inception fields)
        }},
        "phone": "Official contact phone number (show this field only if this data is available and only if there's a null value for the website, address, industry, or inception fields)",
        "ceo_or_key_person": "Name of the CEO or key person in the company (show this field only if this data is available and only if there's a null value for the website, address, industry, or inception fields)",
        "interesting_facts": {"create 2-3 interesting facts about the company or organization"},
        "is_company": true/false,
        "sources": [
            "List of URLs (max 3) where this information was obtained, exclude the logo URL because it has been displayed on the 'logo' field"
        ],
        "confidence": "high/medium/low based on how certain you are this is correct company information"
    }}

    Only return valid JSON without any explanations or formatting around it.
    If you're unsure about specific information, use null for that field rather than guessing.
    If this doesn't appear to be a company or organization, set is_company to false.
    """
    token = client.models.count_tokens(
        model=model,
        contents=prompt,
    )
    print(token)
    response = client.models.generate_content(model=model, contents=prompt)

    return response.text

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

company = input("Enter company name: ")

def extract_company_info(response_text):
    """
    Ekstrak JSON dari response text yang mungkin mengandung ```json ... ```
    dan mengembalikan dict hasil parsing.
    """
    # Cari blok JSON di antara ```json ... ```
    match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # fallback: cari blok JSON langsung
        match = re.search(r"(\{.*\})", response_text, re.DOTALL)
        json_str = match.group(1) if match else None

    if json_str:
        try:
            return json.loads(json_str)
        except Exception as e:
            print(f"JSON parse error: {e}")
            return {}
    return {}

print(extract_company_info(get_company_info_with_tavily(company)))