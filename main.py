import time
import json
import logging
import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from openai import OpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# -------------------------
# Configuration Management
# -------------------------
def load_config():
    """Load API configuration from config.json file."""
    config_file = "config.json"
    
    if not os.path.exists(config_file):
        logger.error(f"Config file '{config_file}' not found. Please create it with your API credentials.")
        raise FileNotFoundError(f"Missing required file: {config_file}")
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Error reading {config_file}: {e}")
        raise
    
    # Validate required fields
    required_fields = ["api_key", "api_base", "model_name"]
    missing_fields = [field for field in required_fields if field not in config or not config[field]]
    
    if missing_fields:
        logger.error(f"Missing required fields in {config_file}: {', '.join(missing_fields)}")
        raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")
    
    api_key = config.get("api_key")
    api_base = config.get("api_base")
    model_name = config.get("model_name")
    
    logger.info(f"Loaded configuration from {config_file}")
    return api_key, api_base, model_name

API_KEY, API_BASE, MODEL_NAME = load_config()

logger.info(f"Using API endpoint: {API_BASE}")
logger.info(f"Using model: {MODEL_NAME}")

# Initialize OpenAI-compatible client
client = OpenAI(api_key=API_KEY, base_url=API_BASE)

# -------------------------
# Helper: Get realistic browser headers
# -------------------------
def get_headers():
    """Return realistic browser headers to avoid 403 blocks."""
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }

# -------------------------
# 1. LLM: generate search queries
# -------------------------
def generate_search_queries(user_prompt):
    """
    Input: high-level user prompt
    Output: list of search query URLs (strings)
    """
    logger.info(f"Generating search queries for: {user_prompt}")
    
    message = client.chat.completions.create(
        model=MODEL_NAME,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""You are a PhD search query generator for FindAPhD.com.
                
                Given the user's request, generate 4 specific, relevant search query URLs for FindAPhD based on keywords.
                
                User request: {user_prompt}
                
                Return ONLY a JSON list of URLs (strings) in this format:
                [
                "https://www.findaphd.com/phds/united-kingdom/?g0w900&Keywords=llm+optimisation",
                "https://www.findaphd.com/phds/united-kingdom/?g0w900&Keywords=machine+learning"
                ]

                Make sure URLs are properly formatted with URL encoding for spaces (+) and special characters."""
            }
        ]
    )
    
    response_text = message.choices[0].message.content
    print(response_text)
    queries = json.loads(response_text.removeprefix("```json").removesuffix("```"))
    logger.debug(f"LLM response for queries: {response_text}")
    
    # Parse the JSON response
    logger.info(f"Generated {len(queries)} search queries")
    return queries

# -------------------------
# 2. Scraper: get project links from search results
# -------------------------
def get_project_links(search_url):
    """
    Fetch search results page and extract all project links.
    """
    logger.info(f"Fetching project links from: {search_url}")
    
    try:
        response = requests.get(search_url, headers=get_headers(), timeout=10)
        response.raise_for_status()
        time.sleep(3)  # increased polite delay
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # extract <a> tags pointing to project pages
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if "/phds/" in href:  # crude filter for MVP
                full_url = href if href.startswith('http') else "https://www.findaphd.com" + href
                if full_url not in links:  # avoid duplicates
                    links.append(full_url)
        
        logger.info(f"Found {len(links)} project links")
        return links
    
    except requests.RequestException as e:
        logger.error(f"Error fetching {search_url}: {e}")
        return []

# -------------------------
# 3. Scraper: get clean text from project page
# -------------------------
def get_clean_text(project_url):
    """
    Fetch project page and extract clean, visible text.
    """
    logger.info(f"Extracting text from: {project_url}")
    
    try:
        response = requests.get(project_url, headers=get_headers(), timeout=10)
        response.raise_for_status()
        time.sleep(3)  # increased polite delay
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # remove noise
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        # extract visible text from meaningful tags
        text_elements = []
        for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li']):
            text = tag.get_text(strip=True)
            if text and len(text) > 10:  # filter out very short snippets
                text_elements.append(text)
        
        clean_text = "\n".join(text_elements)
        logger.info(f"Extracted {len(text_elements)} text elements")
        return clean_text
    
    except requests.RequestException as e:
        logger.error(f"Error fetching {project_url}: {e}")
        return ""

# -------------------------
# 4. LLM: extract structured data
# -------------------------
def extract_project_info(text_blob, project_url):
    """
    Input: clean text blob from project page
    Output: structured dict with fields like:
        title, university, supervisor, funding, alignment
    """
    logger.info(f"Extracting structured info from project")
    
    if not text_blob or len(text_blob) < 50:
        logger.warning(f"Text blob too short for extraction")
        return None
    
    # Truncate if too long to avoid token limits
    text_blob = text_blob[:4000]
    
    message = client.chat.completions.create(
        model=MODEL_NAME,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""Extract structured information from this PhD project description.

Project text:
{text_blob}

Return ONLY a JSON object with these fields (use null for missing info):
{{
  "title": "Project title",
  "university": "University name",
  "supervisor": "Supervisor name(s)",
  "funding": "Funding information or null if not mentioned",
  "international_eligible": "true/false/null - is international funding available?",
  "alignment_score": 0-10 (how aligned with AI/ML/data science based on the text),
  "subject_area": "Main subject area (e.g., Machine Learning, NLP, CV)",
  "key_skills": "Key skills mentioned or required"
}}"""
            }
        ]
    )
    
    response_text = message.choices[0].message.content
    logger.debug(f"LLM response for extraction: {response_text[:200]}")
    
    try:
        project_info = json.loads(response_text)
        return project_info
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        return None

# -------------------------
# 5. Main agent workflow
# -------------------------
def main_agent(user_prompt, max_projects=None):
    """
    Main agent workflow that orchestrates the full pipeline.
    """
    logger.info("=" * 60)
    logger.info(f"Starting PhD Scraper Agent")
    logger.info(f"User request: {user_prompt}")
    logger.info("=" * 60)
    
    all_projects = []
    
    # Step 1: LLM generates search queries
    try:
        search_queries = generate_search_queries(user_prompt)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse search queries from LLM: {e}")
        return
    
    # Step 2-4: Process each search query
    for query_idx, query_url in enumerate(search_queries, 1):
        logger.info(f"\n[Query {query_idx}/{len(search_queries)}] Processing: {query_url}")
        
        # Step 2: Scraper gets project links
        project_links = get_project_links(query_url)
        
        if not project_links:
            logger.warning(f"No project links found for query {query_idx}")
            continue
        
        # Process each project link
        for link_idx, url in enumerate(project_links, 1):
            if max_projects and len(all_projects) >= max_projects:
                logger.info(f"Reached max_projects limit ({max_projects})")
                break
            
            logger.info(f"\n  [Project {link_idx}/{len(project_links)}] Processing: {url}")
            
            # Step 3: Scraper gets clean text
            text_blob = get_clean_text(url)
            
            if not text_blob:
                logger.warning(f"Could not extract text from {url}")
                continue
            
            # Step 4: LLM extracts structured info
            project_info = extract_project_info(text_blob, url)
            
            if project_info:
                project_info['url'] = url
                all_projects.append(project_info)
                logger.info(f"  ✓ Successfully extracted: {project_info.get('title', 'Unknown')}")
            else:
                logger.warning(f"Failed to extract info from {url}")
        
        if max_projects and len(all_projects) >= max_projects:
            break
    
    # Step 5: Save results to CSV
    logger.info("\n" + "=" * 60)
    if all_projects:
        df = pd.DataFrame(all_projects)
        df.to_csv("phd_listings.csv", index=False)
        logger.info(f"✓ Saved {len(all_projects)} projects to phd_listings.csv")
        logger.info(f"Columns: {', '.join(df.columns)}")
    else:
        logger.warning("No projects were extracted")
    logger.info("=" * 60)
    
    return all_projects

# -------------------------
# Entry point
# -------------------------
if __name__ == "__main__":
    # Example usage
    user_input ='subject should be AI and machine learning or LLMs or multimodal ai or things related to artificial intelligence'
    
    results = main_agent(user_input, max_projects=5)
    
    if results:
        print(f"\nExtracted {len(results)} projects:")
        for i, project in enumerate(results, 1):
            print(f"\n{i}. {project.get('title', 'Unknown')} - {project.get('university', 'Unknown')}")
