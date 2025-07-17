from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import LLMChain
from langchain.agents import AgentExecutor, create_tool_calling_agent

from datetime import datetime, time, timedelta
import os
from dotenv import load_dotenv, find_dotenv
from typing import List, Dict, Optional
from collections import defaultdict
from pydantic import BaseModel, Field, ValidationError
from utils import from_hhmm, calculate_duration_minutes
from scrapers import albany_scraper
import redis
import json

# Load .env
_ = load_dotenv(find_dotenv())
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_redis_client = None
_scrape_cache_ttl_seconds = 3600 # Default to 1 hour, will be overridden by app.py

def get_tennis_court_availability(date: str = None, city_names:List[str]=None) -> List[Dict]:
    """
    Fetches tennis court availability for a given date, using Redis cache.
    The date should be provided in 'MM/DD/YYYY' format (e.g., '06/21/2025').
    If no date is provided, it defaults to today's date.
    The web scraping always starts at 05:00 AM.
    Returns a list of dictionaries, each representing a court availability slot.
    """
    global _redis_client, _scrape_cache_ttl_seconds # Declare intent to modify globals

    if _redis_client is None:
        print("WARNING: Redis client not initialized in agent.py. Scraping cache will NOT work.")

    if not city_names:
        # TODO later add other cities you can scrape
        city_names = ["Albany"]

    if date is None:
        target_date = datetime.now().strftime("%m/%d/%Y")
    else:
        try:
            datetime.strptime(date, "%m/%d/%Y")
            target_date = date
        except ValueError:
            return [{"message": f"Error: Invalid date format provided. Please use MM/DD/YYYY (e.g., 06/21/2025). You provided: {date}"}]

    availability_data = []
    for city in city_names:
        # Create a unique cache key for each date and city
        cache_key = f"scrape_cache:{target_date}:{city.lower()}"

        cached_rows = None
        if _redis_client:
            cached_rows_json = _redis_client.get(cache_key)
            if cached_rows_json:
                try:
                    cached_rows = json.loads(cached_rows_json)
                    print(f"INFO: Cache hit for scrape_cache:{cache_key}")
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"WARNING: Corrupted cache data for {cache_key}: {e}. Will re-scrape.")
                    # In case of corruption, delete the bad key to force re-scrape
                    _redis_client.delete(cache_key)
            else:
                print(f"INFO: Cache miss for scrape_cache:{cache_key}. Scraping...")

        if cached_rows is None: # If not in cache or Redis is not available or data was corrupted
            if city.lower() == "albany":
                rows = albany_scraper(target_date)
                if _redis_client and rows and not any("message" in r for r in rows): # Only cache if scrape was successful and not an error message
                    _redis_client.set(cache_key, json.dumps(rows), ex=_scrape_cache_ttl_seconds) # Cache with TTL
                    print(f"INFO: Cached {len(rows)} entries for scrape_cache:{cache_key}")
                elif _redis_client:
                    print(f"WARNING: Did not cache for {cache_key} due to empty rows or error message from scraper.")
                availability_data.extend(rows)
            # TODO: Add logic for other cities like Berkeley, Oakland
        else:
            availability_data.extend(cached_rows)

    return availability_data



class FilteredCourtSlot(BaseModel):
    """Represents a single filtered court availability slot."""
    date: str = Field(..., description="The date of the slot in MM/DD/YYYY format.")
    city_name: str = Field(..., description="The name of the city where the court is located.")
    park_name: str = Field(..., description="The name of the park where the court is located.")
    court_name: str = Field(..., description="The name or identifier of the tennis court.")
    start_time: str = Field(..., description="The start time of the slot in HH:MM (24-hour) format.")
    end_time: str = Field(..., description="The end time of the slot in HH:MM (24-hour) format.")
    availability: str = Field(..., description="The availability status ('Available' or 'Unavailable').")


def merge_consecutive_slots(filtered_rows: List[FilteredCourtSlot]) -> List[FilteredCourtSlot]:
    """
    Merge consecutive available time slots for the same court and park.

    Args:
        filtered_rows: A list of FilteredCourtSlot objects representing filtered court availabilities.

    Returns:
        A new list of FilteredCourtSlot objects where consecutive time slots are merged.
    """

    merged = []
    grouped = defaultdict(list)

    # Group available slots by date, city, park, and court
    for row in filtered_rows:
        if row.availability == "Available": # Accessing attribute
            key = (row.date, row.city_name, row.park_name, row.court_name) # Accessing attributes
            grouped[key].append((row.start_time, row.end_time)) # Accessing attributes

    # Iterate through grouped intervals and merge
    for (date, city, park, court), intervals in grouped.items():
        intervals.sort()

        if not intervals:
            continue

        merged_intervals = []
        current_start, current_end = intervals[0]

        for start, end in intervals[1:]:
            if from_hhmm(start) == from_hhmm(current_end):
                current_end = end
            else:
                merged_intervals.append((current_start, current_end))
                current_start, current_end = start, end

        merged_intervals.append((current_start, current_end))

        # Format and append merged intervals to the final list, creating FilteredCourtSlot instances
        for start, end in merged_intervals:
            merged.append(FilteredCourtSlot(
                date=date,
                city_name=city,
                park_name=park,
                court_name=court,
                start_time=start,
                end_time=end,
                availability="Available"
            ))

    return merged


class FilterInput(BaseModel):
    """Input schema for the filter_court_availability tool."""
    date: str = Field(..., description="Date of the slot in MM/DD/YYYY format.")
    city_names: Optional[List[str]] = Field(None, description="List of city names to filter by.")
    min_start_time: Optional[str] = Field(None, description="Minimum start time for filtering (HH:MM 24-hour format).")
    max_end_time: Optional[str] = Field(None, description="Maximum end time for filtering (HH:MM 24-hour format).")
    park_name: Optional[str] = Field(None, description="Specific park name to filter by.")
    court_name: Optional[str] = Field(None, description="Specific court name to filter by.")
    min_duration_minutes: Optional[int] = Field(None, description="Minimum duration in minutes for available slots.")
    cache: Optional[Dict] = Field(None, description="Cache")


def filter_court_availability(
        date: str,
        city_names: Optional[List[str]] = None,
        min_start_time: Optional[str] = None,
        max_end_time: Optional[str] = None,
        park_name: Optional[str] = None,
        court_name: Optional[str] = None,
        min_duration_minutes: Optional[int] = None,
) -> List[FilteredCourtSlot]:
    """
    Filters a list of court availability slots based on specified criteria.
    """
    availability_data = get_tennis_court_availability(date=date, city_names=city_names)

    filtered_slots_list = []

    min_start_dt = from_hhmm(min_start_time) if min_start_time else None
    max_end_dt = from_hhmm(max_end_time) if max_end_time else None

    for slot in availability_data:
        if "message" in slot:
            continue

        if slot.get("availability") != "Available":
            continue

        match = True

        # Date filtering (already passed to get_tennis_court_availability, so might be redundant here if the scraper is perfect, but good for robustness)
        if slot.get("date") != date:
            match = False

        if city_names:
            city_match = False
            for city_name_filter in city_names:
                if city_name_filter.lower() in slot.get("city_name", "").lower():
                    city_match = True
                    break
            if not city_match:
                match = False

        if park_name and park_name.lower() not in slot.get("park_name", "").lower():
            match = False

        if court_name and court_name.lower() not in slot.get("court_name", "").lower():
            match = False

        if min_start_dt:
            slot_start_dt = from_hhmm(slot["start_time"])
            if slot_start_dt < min_start_dt:
                match = False

        if max_end_dt:
            slot_end_dt = from_hhmm(slot["end_time"])
            if slot_end_dt > max_end_dt:
                match = False

        # # TODO - this should be after merging
        # if min_duration_minutes is not None:
        #     duration = calculate_duration_minutes(slot["start_time"], slot["end_time"])
        #     if duration < min_duration_minutes:
        #         match = False

        if match:
            filtered_slots_list.append(FilteredCourtSlot(
                date=slot["date"],
                city_name=slot["city_name"],
                park_name=slot["park_name"],
                court_name=slot["court_name"],
                start_time=slot["start_time"],
                end_time=slot["end_time"],
                availability=slot["availability"]
            ))

    merged_slots = merge_consecutive_slots(filtered_slots_list)

    return merged_slots


# --- LLM Setup ---
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0, api_key=OPENAI_API_KEY)


# Prompt with tool invocation
def get_current_date_prompt(current_date):

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         f"You are a helpful tennis court booking assistant.\n\n"
         "Your goal is to help users:\n"
         " - find available courts for a sport (usually tennis or pickleball)\n"
         " - request specific courts and times for booking\n"
         " - answer questions about court availability\n\n"
         "Users may phrase their requests in different ways. Your job is to:\n"
         "1. Extract user preferences (e.g., date, time window, duration, location, or court name).\n"
         "2. If the user doesn't give a date, assume today. If they don’t say how long, assume 1 hour.\n"
         "3. Clearly present the final results to the user."
         "   * Follow the grouping level city Name, Park name, and the under each court name present the Available time slots"
         "   * If no slots match the user's criteria after filtering and merging, politely explain that no availability was found."
         "   * If any tool returns a dictionary with a message key (indicating an error or no data), relay that message to the user directly."
         "6. when the user chooses a specific court and time from the options, ask again to confirm and make sure it's bookable by using your tools.\n"
         "7. If what user wants is not possible , show other courts in the area that are available in the time range and other times that the specific park/court has availability of ."
         "Maintain conversation context from previous turns. If you need more information, ask clarifying questions."
    
         f"""
             **Important Considerations:**
                * Convert all times to 24-hour HH:MM format before passing them as arguments to tools (e.g., "5 PM" becomes "17:00", "9 AM" becomes "09:00").
                * Be conversational and helpful in your responses.
                * Current date: {current_date}.
                * Figure out the day of the week that today is and then what date it would correspond to if the user says "this friday, this sunday" etc.
                * Current location: Albany, California, United States.
         """
         ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{message}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])
    return prompt

# Create the agent
def get_agent_executor(user_specific_memory, user_specific_tools, current_date_str, redis_client_from_app, scrape_cache_ttl):
    """Returns a new AgentExecutor instance with user-specific memory, tools, and a dynamic prompt."""
    global _redis_client, _scrape_cache_ttl_seconds # Access the global variables
    _redis_client = redis_client_from_app # Set the global redis client
    _scrape_cache_ttl_seconds = scrape_cache_ttl # Set the global scrape cache TTL

    print(current_date_str)
    prompt = get_current_date_prompt(current_date_str)

    base_agent = create_tool_calling_agent(llm, user_specific_tools, prompt)

    return AgentExecutor(
        agent=base_agent,
        tools=user_specific_tools,
        verbose=True,
        memory=user_specific_memory,
        return_intermediate_steps=True
    )


