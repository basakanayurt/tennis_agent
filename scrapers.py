from matplotlib.lines import lineStyles
from utils import from_hhmm, to_hhmm, calculate_duration_minutes
from langchain_community.document_loaders import WebBaseLoader
import re
import requests
import os
# Load .env
from dotenv import load_dotenv, find_dotenv
import urllib.parse
from bs4 import BeautifulSoup

_ = load_dotenv(find_dotenv())

def albany_scraper(target_date):
    begintime_url_param = "05:00 am"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Referer": "https://caalbanyweb.myalbanyweb.myvscloud.com/",
        "Origin": "https://caalbanyweb.myvscloud.com",
        "Accept-Language": "en-US,en;q=0.9",
        # "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "DNT": "1",  # Do Not Track request header
        "Upgrade-Insecure-Requests": "1",
        "Sec-GPC": "1"  # Global Privacy Control
    }


    original_base_url = f"https://caalbanyweb.myvscloud.com/webtrac/web/search.html?module=FR&FRClass=TENNI&date={target_date}&begintime={begintime_url_param.replace(' ', '%20')}&Action=Start"

    # base_url = f"https://app.scrapingbee.com/api/v1/?api_key={SCRAPERAPI_API_KEY}&url={original_base_url}&render_js=false"

##############################################################################################################################

    host = 'brd.superproxy.io'
    port = 33335
    BRIGHTDATA_USERNAME = os.getenv("BRIGHTDATA_USERNAME")  # e.g., brd-customer-xxxx-zone-xxxx
    BRIGHTDATA_PASSWORD = os.getenv("BRIGHTDATA_PASSWORD")

    proxy_url = f'http://{BRIGHTDATA_USERNAME}:{BRIGHTDATA_PASSWORD}@{host}:{port}'

    proxies = {
        'http': proxy_url,
        'https': proxy_url
    }

    response = requests.get(original_base_url, proxies=proxies, verify=False)


    # from readability import Document
    # import io
    # from langchain_community.document_loaders import UnstructuredHTMLLoader


    def fetch_and_clean_webbased_style(response) -> str:
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove scripts and styles
        for tag in soup(["script", "style", "head", "title", "meta", "[document]"]):
            tag.decompose()

        # Get text with spaces (no forced newlines)
        text = soup.get_text(separator="\n")
        # Collapse multiple spaces/newlines into one space
        text = re.sub(r'\n\s*\n', '\n', text.strip())
        cleaned = text.strip()
        return cleaned

    s = fetch_and_clean_webbased_style(response)
    print(s)

    # loader = WebBaseLoader(original_base_url)
    #
    # docs = loader.load()
    # print(docs)

    # if not docs:
    #     print("Failed to load documents. Returning empty list.")
    #     return [{"message": "No availability found or failed to load from the website."}]

    # s = docs[0].page_content

    # pattern_available = r'(?P<start>\d{1,2}:\d{2} [ap]m)\s*-\s*(?P<end>\d{1,2}:\d{2} [ap]m)(?!Unavailable)'
    # pattern_unavailable = r'(?P<start>\d{1,2}:\d{2} [ap]m)\s*-\s*(?P<end>\d{1,2}:\d{2} [ap]m)(?P<unavailable>Unavailable)?'

    rows = []
    court_name = ""
    park_name = ""
    city_name = "Albany"

    # Regex for matching time slots
    time_pattern = r'(\d{1,2}:\d{2} [ap]m)\s*-\s*(\d{1,2}:\d{2} [ap]m)'

    lines = s.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for Court Name
        if "Tennis Court" in line or "OV Tennis Court" in line or "Tennis Terrace" in line:
            court_name = line

        # Check for Park Name
        elif "Park" in line:
            park_name = line

        # Check for Time Slots
        elif re.match(time_pattern, line):
            match = re.match(time_pattern, line)
            start_time_str = match.group(1)
            end_time_str = match.group(2)

            # Determine availability by checking the next line
            availability = "Available"
            if i + 1 < len(lines) and lines[i + 1] == "Unavailable":
                availability = "Unavailable"
                # Skip the 'Unavailable' line as we've already processed it
                i += 1

            rows.append({
                "city_name": city_name,
                "park_name": park_name,
                "court_name": court_name,
                "start_time": to_hhmm(start_time_str),
                "end_time": to_hhmm(end_time_str),
                "date": target_date,
                "availability": availability
            })

        i += 1

    #
    #
    # for line in s_.split("\n"):
    #     if "Tennis Court" in line or "OV Tennis Court" in line or "Tennis Terrace" in line:
    #         court_name = line.strip()
    #     elif "Park" in line:
    #         park_name = line.strip()
    #     elif "Book Now" in line:
    #         for m in re.finditer(pattern_available, line):
    #             rows.append({
    #                 "city_name": city_name,
    #                 "park_name": park_name,
    #                 "court_name": court_name,
    #                 "start_time": to_hhmm(m.group("start")),
    #                 "end_time": to_hhmm(m.group("end")),
    #                 "date": target_date,
    #                 "availability": "Available"
    #             })
    #         for m in re.finditer(pattern_unavailable, line):
    #             if m.group("unavailable"):
    #                 rows.append({
    #                     "city_name": city_name,
    #                     "park_name": park_name,
    #                     "court_name": court_name,
    #                     "start_time": to_hhmm(m.group("start")),
    #                     "end_time": to_hhmm(m.group("end")),
    #                     "date": target_date,
    #                     "availability": "Unavailable"
    #                 })
    #
    # print(f"Generated data with {len(rows)} entries")
    return rows
