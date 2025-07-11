from utils import from_hhmm, to_hhmm, calculate_duration_minutes
from langchain_community.document_loaders import WebBaseLoader
import re


def albany_scraper(target_date):
    begintime_url_param = "05:00 am"
    base_url = f"https://caalbanyweb.myvscloud.com/webtrac/web/search.html?module=FR&FRClass=TENNI&date={target_date}&begintime={begintime_url_param.replace(' ', '%20')}&Action=Start"

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

    print(f"Loading data from: {base_url}")
    loader = WebBaseLoader(base_url, requests_kwargs={"headers": headers})
    docs = loader.load()

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
