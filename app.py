# app.py

from flask import Flask, request, jsonify, render_template, session
from datetime import datetime, timedelta
import os
import uuid
from functools import partial
from langchain.memory import ConversationBufferMemory
from langchain_core.exceptions import OutputParserException
from langchain_core.tools import tool
from typing import List, Dict, Optional

# Import the core agent logic and the tool's base definition
from agent import get_agent_executor, filter_court_availability, FilterInput

# --- Global Dictionaries for User-Specific Data ---
user_memories = {}
user_caches = {}

# Create the Flask app instance
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))


# --- Flask Routes ---

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/chat', methods=['POST'])
def chat():
    # --- Memory Management ---
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id

    if user_id not in user_memories:
        print(f"INFO: Initializing new session for user_id: {user_id}")
        user_memories[user_id] = {
            'memory': ConversationBufferMemory(memory_key="chat_history", input_key="message", return_messages=True),
            'last_used': datetime.now()
        }
        user_caches[user_id] = {}

    user_memories[user_id]['last_used'] = datetime.now()

    user_specific_memory = user_memories[user_id]['memory']
    user_specific_cache = user_caches[user_id]

    user_message = request.get_json().get('message')
    if not user_message:
        return jsonify({'response': 'Please provide a message.'}), 400

    try:
        # --- Get the correct dates ---
        today = datetime.now()
        current_date_str = today.strftime('%m/%d/%Y')

        # --- The key change: Create a user-specific tool with the cache ---
        # 1. Use partial to pre-set the cache argument
        partial_tool = partial(
            filter_court_availability,
            cache=user_specific_cache
        )

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
            return partial_tool(
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
        )

        response = agent_executor.invoke({"message": user_message})
        output = response["output"]
        return jsonify({'response': output})
    except OutputParserException as e:
        print(f"Error: {e}")
        return jsonify({'response': 'Sorry, I couldn\'t process that request.'}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'response': 'An error occurred while processing your request.'}), 500


# if __name__ == '__main__':
#     app.run(debug=True)