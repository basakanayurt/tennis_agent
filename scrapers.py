from utils import from_hhmm, to_hhmm, calculate_duration_minutes
from langchain_community.document_loaders import WebBaseLoader
import re
import requests
import os
# Load .env
from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())
# SCRAPERAPI_API_KEY = os.getenv("SCRAPERAPI_API_KEY")
# SCRAPERAPI_API_KEY = os.getenv("SCRAPINGBEE_API_KEY")

def albany_scraper(target_date):
    begintime_url_param = "05:00 am"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Referer": "https://caalbanyweb.myalbanyweb.myvscloud.com/",
        "Origin": "https://caalbanyweb.myvscloud.com",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }


    original_base_url = f"https://caalbanyweb.myvscloud.com/webtrac/web/search.html?module=FR&FRClass=TENNI&date={target_date}&begintime={begintime_url_param.replace(' ', '%20')}&Action=Start"

    # base_url = f"https://app.scrapingbee.com/api/v1/?api_key={SCRAPERAPI_API_KEY}&url={original_base_url}&render_js=false"

##############################################################################################################################
    iproyal_username =  os.getenv("IPROYAL_USERNAME")
    iproyal_password = os.getenv("IPROYAL_PASSWORD")
    iproyal_proxy_host = os.getenv("IPROYAL_HOSTNAME")
    iproyal_proxy_port = os.getenv("IPROYAL_PORT")

    base_url = f"http://{iproyal_username}:{iproyal_password}@{iproyal_proxy_host}:{iproyal_proxy_port}"

    # try:
    #     response = requests.get(base_url, timeout=100)#, headers=headers,)
    #
    #     # --- NEW DEBUGGING LINES ---
    #     print(f"Status Code: {response.status_code}")
    #     print(f"Response Content Length: {len(response.text)}")
    #     # print(f"Response Content (first 500 chars):\n{response.text[:500]}")
    #
    #     response.raise_for_status()  # This will raise an exception for bad status codes (e.g., 4xx or 5xx)
    #
    #     # s = response.text
    #     # print(s)
    #
    # except requests.exceptions.RequestException as e:
    #     print(f"An error occurred: {e}")
    #     return [{"message": "Failed to load from the website due to a network error."}]
    #

    # loader = WebBaseLoader(
    #     original_base_url,
    #     proxies={
    #         "http": base_url,
    #         "https": base_url,
    #     },
    # )

    proxies = {
        "http": base_url,
        "https": base_url,
    }

    loader = WebBaseLoader(
        original_base_url,
        requests_kwargs={
            "proxies": proxies,
            "headers": headers,
        }
    )


    # loader = WebBaseLoader(base_url) #, requests_kwargs={"headers": headers})

    docs = loader.load()
    print(docs)

    if not docs:
        print("Failed to load documents. Returning empty list.")
        return [{"message": "No availability found or failed to load from the website."}]

    s = docs[0].page_content

    pattern_available = r'(?P<start>\d{1,2}:\d{2} [ap]m)\s*-\s*(?P<end>\d{1,2}:\d{2} [ap]m)(?!Unavailable)'
    pattern_unavailable = r'(?P<start>\d{1,2}:\d{2} [ap]m)\s*-\s*(?P<end>\d{1,2}:\d{2} [ap]m)(?P<unavailable>Unavailable)?'

    rows = []
    court_name = ""
    park_name = ""
    city_name = "Albany"

    for line in s.split("\n"):
        if "Tennis Court" in line or "OV Tennis Court" in line or "Tennis Terrace" in line:
            court_name = line.strip()
        elif "Park" in line:
            park_name = line.strip()
        elif "Book Now" in line:
            for m in re.finditer(pattern_available, line):
                rows.append({
                    "city_name": city_name,
                    "park_name": park_name,
                    "court_name": court_name,
                    "start_time": to_hhmm(m.group("start")),
                    "end_time": to_hhmm(m.group("end")),
                    "date": target_date,
                    "availability": "Available"
                })
            for m in re.finditer(pattern_unavailable, line):
                if m.group("unavailable"):
                    rows.append({
                        "city_name": city_name,
                        "park_name": park_name,
                        "court_name": court_name,
                        "start_time": to_hhmm(m.group("start")),
                        "end_time": to_hhmm(m.group("end")),
                        "date": target_date,
                        "availability": "Unavailable"
                    })

    print(f"Generated data with {len(rows)} entries")
    return rows
