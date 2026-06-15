import os
import json
import streamlit as st
import anthropic
from google.cloud import bigquery

GCP_PROJECT = "project-6a3a4778-6bf8-49b1-984"
DATASET = "dog_breeds_curated"

SYSTEM_PROMPT = """You are a friendly and knowledgeable dog breed advisor named Pawly. \
You help people find their perfect dog breed using real data from a database of over 600 breeds.

You have access to two BigQuery tables via the `query_bigquery` tool:
- `mart_breeds`: breed_name, size_class (Toy/Small/Medium/Large/Giant), weight_min_kg, weight_max_kg, \
height_min_cm, height_max_cm, life_span_min, life_span_max, breed_group
- `mart_temperaments`: breed_name, temperament (one row per breed per trait, all lowercased)

Your approach:
1. Greet the user warmly and start asking about their lifestyle — one or two questions at a time.
2. Explore: living space (apartment/house/garden), activity level, experience with dogs, \
family situation (kids, elderly, other pets), size preference, tolerance for shedding/grooming, \
how many hours alone the dog will be.
3. Once you have a clear picture, use `query_bigquery` to find matching breeds. \
Write SQL that filters by size, temperament tags, weight, and life span as appropriate.
4. Present 3–5 top recommendations with a short explanation for each — why they match.
5. Invite follow-up questions: the user can ask about a specific breed, compare two breeds, etc.

Be warm, conversational, and concise. Never dump raw SQL or table data on the user — \
always turn the results into friendly, human-readable advice."""

TOOLS = [
    {
        "name": "query_bigquery",
        "description": (
            "Run a SQL query against the dog breed BigQuery database to retrieve breed information. "
            "Use this to find breeds matching the user's preferences. "
            f"Tables: `{GCP_PROJECT}.{DATASET}.mart_breeds` and "
            f"`{GCP_PROJECT}.{DATASET}.mart_temperaments`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": (
                        "Standard SQL query. "
                        f"mart_breeds columns: breed_name, size_class, weight_min_kg, weight_max_kg, "
                        f"height_min_cm, height_max_cm, life_span_min, life_span_max, breed_group. "
                        f"mart_temperaments columns: breed_name, temperament (lowercased). "
                        f"Always qualify table names with `{GCP_PROJECT}.{DATASET}.`."
                    ),
                }
            },
            "required": ["sql"],
        },
    }
]


@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=GCP_PROJECT)


def run_query(sql: str) -> list[dict]:
    client = get_bq_client()
    try:
        rows = client.query(sql).result()
        return [dict(row) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


def call_claude(messages: list[dict], api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect text and tool-use blocks
        tool_use_blocks = []
        text_parts = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        # If Claude wants to use a tool, execute it and loop
        if response.stop_reason == "tool_use" and tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tb in tool_use_blocks:
                sql = tb.input.get("sql", "")
                rows = run_query(sql)
                result_text = json.dumps(rows, default=str)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": result_text,
                    }
                )

            messages.append({"role": "user", "content": tool_results})
            continue  # loop back so Claude can synthesize

        # Claude is done — return the text
        return " ".join(text_parts).strip()


# ── UI ────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Pawly — Dog Breed Advisor", page_icon="🐾", layout="centered")

st.title("🐾 Pawly — Dog Breed Advisor")
st.caption("Powered by Claude AI + live BigQuery data")

with st.sidebar:
    st.header("Settings")
    api_key = st.text_input(
        "Anthropic API key",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Get yours at console.anthropic.com",
    )
    st.divider()
    st.markdown(
        "**Data source:** BigQuery `dog_breeds_curated`  \n"
        "**Model:** Claude Sonnet 4.6  \n"
        "**Breeds in database:** 600+"
    )
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat_history = []
        st.rerun()

# Session state
if "messages" not in st.session_state:
    st.session_state.messages = []  # full API history (with tool results)
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # display-only (role + text)

# Render existing messages
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Greeting on first load
if not st.session_state.chat_history:
    if not api_key:
        st.info("Enter your Anthropic API key in the sidebar to get started.")
    else:
        with st.spinner("Pawly is waking up..."):
            seed = [{"role": "user", "content": "Hello!"}]
            greeting = call_claude(seed, api_key)
            st.session_state.messages.extend([
                {"role": "user", "content": "Hello!"},
                {"role": "assistant", "content": greeting},
            ])
            st.session_state.chat_history.append({"role": "assistant", "content": greeting})
        with st.chat_message("assistant"):
            st.markdown(greeting)

# Chat input
if prompt := st.chat_input("Tell me about your lifestyle..."):
    if not api_key:
        st.error("Please enter your Anthropic API key in the sidebar first.")
        st.stop()

    # Show user message
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Add to full API history and call Claude
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Pawly is thinking..."):
            reply = call_claude(st.session_state.messages, api_key)

        # The call_claude function already appended assistant + tool turns to messages.
        # Append the final assistant reply for the next turn.
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.markdown(reply)
