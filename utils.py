from datetime import datetime, timedelta
from itertools import groupby
from operator import itemgetter
from collections import defaultdict
from datetime import timedelta

from langchain.tools import tool
from datetime import datetime, timedelta


def normalize_date(date_str: str) -> str:
    """Convert 'today' and 'tomorrow' to MM/DD/YYYY format"""
    today = datetime.today()
    if date_str.lower() == "today":
        return today.strftime("%m/%d/%Y")
    elif date_str.lower() == "tomorrow":
        return (today + timedelta(days=1)).strftime("%m/%d/%Y")
    return date_str


def to_hhmm(tstr):
    """Converts a time string (e.g., '09:00 AM', '09:00') to HH:MM (24-hour) format."""
    try:
        # Try parsing as HH:MM AM/PM
        dt = datetime.strptime(tstr.strip(), "%I:%M %p")
    except ValueError:
        try:
            # Try parsing as HH:MM (24-hour)
            dt = datetime.strptime(tstr.strip(), "%H:%M")
        except ValueError:
            raise ValueError(f"Invalid time format: {tstr}. Expected 'HH:MM AM/PM' or 'HH:MM'.")
    return dt.strftime("%H:%M")


def from_hhmm(hhmm_str):
    """Converts an HH:MM (24-hour) string to datetime.time object."""
    return datetime.strptime(hhmm_str, "%H:%M").time()


def calculate_duration_minutes(start_str, end_str):
    """Calculates the duration in minutes between two HH:MM time strings."""
    start_time = from_hhmm(start_str)
    end_time = from_hhmm(end_str)
    if end_time < start_time:
        time_delta = datetime.combine(datetime.min.date() + timedelta(days=1), end_time) - datetime.combine(
            datetime.min.date(), start_time)
    else:
        time_delta = datetime.combine(datetime.min.date(), end_time) - datetime.combine(datetime.min.date(), start_time)
    return int(time_delta.total_seconds() / 60)


# @tool
# def interpret_user_params(
#     sport: str,
#     date: str,
#     begin_time: str = None,
#     flexible_after: bool = False,
#     flexible_before: bool = False,
#     end_time: str = None,
#     duration_minutes: int = None,
#     location: str = None,
#     parkname: str = None,
#     facility: str = None
# ) -> dict:
#     """
#     Interprets user's booking preferences flexibly.
#
#     Parameters:
#     - sport: 'TENNI' or 'PBALL'
#     - date: Desired booking date (MM/DD/YYYY)
#     - begin_time: HH:MM AM/PM (if specified)
#     - flexible_after: True if user says "after", "starting from", etc.
#     - flexible_before: True if user says "before", "ending by", etc.
#     - end_time: HH:MM AM/PM (if provided in request)
#     - duration_minutes: Duration in minutes (if known). Defaults to 60.
#     - location, parkname, facility: Optional scoping params
#
#     Logic:
#     - Map anything that sounds like  tennis to 'TENNI' and anything that sounds like pickleball to 'PBALL'
#     - If duration is not given but begin_time and end_time are, duration is inferred.
#     - If duration and begin_time are given but not end_time don't infer end_time.
#     - If duration and end_time are given but not begin_time don't infer begin_time.
#     - If neither end_time nor duration is given, assume duration of 60 minutes.
#     - If only end_time is given with flexible_before=True, work backward from that.
#
#     Returns:
#     Structured dict for filtering court slots.
#     """
#
#     def to_dt(time_str):
#         return datetime.strptime(time_str, "%I:%M %p") if time_str else None
#
#     normalized_date = normalize_date(date)
#
#     begin_dt = to_dt(begin_time) if begin_time else None
#     end_dt = to_dt(end_time) if end_time else None
#
#     # Default assumption
#     if duration_minutes is None:
#         if begin_dt and end_dt:
#             duration_minutes = int((end_dt - begin_dt).total_seconds() // 60)
#         else:
#             duration_minutes = 60
#
#
#     return {
#         "sport": sport,
#         "date": normalized_date,
#         "begin_time": begin_time,
#         "flexible_after": flexible_after,
#         "flexible_before": flexible_before,
#         "end_time": end_time,
#         "duration_minutes": duration_minutes,
#         "location": location,
#         "parkname": parkname,
#         "facility": facility,
#     }
