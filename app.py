# app.py

from flask import Flask, request, jsonify, render_template, session
from datetime import datetime, timedelta
import os
import uuid
import json
import redis
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import messages_to_dict, messages_from_dict
from functools import partial
from langchain.memory import ConversationBufferMemory
from langchain_core.exceptions import OutputParserException
from langchain_core.tools import tool
from typing import List, Dict, Optional

# Import the core agent logic and the tool's base definition
from agent import get_agent_executor, filter_court_availability, FilterInput

# --- Global Redis Client ---
# Initialize Redis client once when the app starts
redis_url = os.getenv("REDIS_URL")

# decode_responses=True automatically decodes Redis responses to UTF-8 strings
redis_client = redis.from_url(redis_url, decode_responses=True)
# Ping Redis to check connection (optional, good for debugging startup)
try:
    redis_client.ping()
    print("INFO: Successfully connected to Redis!")
except redis.exceptions.ConnectionError as e:
    print(f"ERROR: Could not connect to Redis: {e}")
    redis_client = None # Set to None if connection fails

# Create the Flask app instance
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

# Set Flask session timeout to 30 minutes (cookie expiration)
app.permanent_session_lifetime = timedelta(minutes=30)

@app.before_request
def make_session_permanent():
    session.permanent = True

# --- Constants for Redis Keys and TTLs ---
CHAT_HISTORY_TTL_SECONDS = int(timedelta(minutes=15).total_seconds()) # Match Flask session lifetime
SCRAPE_CACHE_TTL_SECONDS = int(timedelta(minutes=15).total_seconds()) # Cache scrape for 1 hour


# --- Flask Routes ---

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/chat', methods=['POST'])
def chat():
    # --- Assign user session ---
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
        print(f"INFO: Initializing new session for user_id: {user_id}")
    else:
        print(f"INFO: Existing session for user_id: {user_id}")

    chat_history_key = f"chat_history:{user_id}"
    # --- Load User Memory (Chat History) from Redis ---
    user_specific_memory = None
    if redis_client:
        stored_chat_history_json = redis_client.get(chat_history_key)

        past_messages = []
        if stored_chat_history_json:
            try:
                past_messages_dicts = json.loads(stored_chat_history_json)
                past_messages = messages_from_dict(past_messages_dicts)
                print(f"INFO: Loaded chat history from Redis for user_id: {user_id}")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"WARNING: Could not decode chat history from Redis for user_id {user_id}: {e}. Will start with empty history.")
                pass

        # --- CORRECTED INITIALIZATION ---
        user_specific_memory = ConversationBufferMemory(
            memory_key="chat_history",
            input_key="message",
            return_messages=True,
            chat_memory=ChatMessageHistory(messages=past_messages) # <--- THIS IS THE CORRECT WAY
        )
    else:
        # Fallback to in-memory if Redis not available
        print("WARNING: Redis not available. Using in-memory chat history (will not persist).")
        user_specific_memory = ConversationBufferMemory(
            memory_key="chat_history",
            input_key="message",
            return_messages=True
        )


    # Note: user_caches global is now completely removed. The Redis client will be passed
    # and filter_court_availability will handle caching itself.

    user_message = request.get_json().get('message')
    if not user_message:
        return jsonify({'response': 'Please provide a message.'}), 400

    try:
        # --- Get the correct dates ---
        today = datetime.now()
        current_date_str = today.strftime('%m/%d/%Y')


        # 2. Define a new tool with a clean signature for the LLM
        @tool(args_schema=FilterInput)
        def filter_tool_for_llm(
                date: str,
                city_names: Optional[List[str]] = None,
                min_start_time: Optional[str] = None,
                max_end_time: Optional[str] = None,
                park_name: Optional[str] = None,
                court_name: Optional[str] = None,
                min_duration_minutes: Optional[int] = None
        ) -> List:
            """
            Filters a list of court availability slots based on specified criteria.
            """
            return filter_court_availability( # Call directly, it manages Redis internally
                date=date,
                city_names=city_names,
                min_start_time=min_start_time,
                max_end_time=max_end_time,
                park_name=park_name,
                court_name=court_name,
                min_duration_minutes=min_duration_minutes
            )

        # Get a fresh agent executor with the user's specific tools and memory
        agent_executor = get_agent_executor(
            user_specific_memory,
            [filter_tool_for_llm],  # Pass the new tool here
            current_date_str,
            redis_client,
            SCRAPE_CACHE_TTL_SECONDS
        )

        response = agent_executor.invoke({"message": user_message})
        output = response["output"]

        # --- Save User Memory (Chat History) to Redis ---
        if redis_client and user_specific_memory:
            current_chat_history_dicts = messages_to_dict(user_specific_memory.chat_memory.messages)
            redis_client.set(chat_history_key, json.dumps(current_chat_history_dicts), ex=CHAT_HISTORY_TTL_SECONDS)
            print(f"INFO: Saved chat history to Redis for user_id: {user_id}")

        return jsonify({'response': output})

    except OutputParserException as e:
        print(f"Error: {e}")
        return jsonify({'response': 'Sorry, I couldn\'t process that request.'}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'response': 'An error occurred while processing your request.'}), 500

# if __name__ == '__main__':
#     app.run(debug=True)