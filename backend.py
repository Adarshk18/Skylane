import operator
from tools.flight_tool import format_flight, resolve_location, search_flights
from tools.tavily_tool import tavily_search
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, START, END
from psycopg.rows import dict_row
import psycopg
import uuid
from typing import TypedDict, Annotated
from dotenv import load_dotenv
import os
import certifi

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage


class FlightSearchParams(BaseModel):
    origin: str = Field(
        description="Departure city, airport, or country explicitly specified by the user"
    )
    destination: str = Field(
        description="Arrival city, airport, or country explicitly specified by the user"
    )
    departure_date: Optional[str] = Field(
        default=None,
        description="Departure date in YYYY-MM-DD format, or null if not specified"
    )


def get_database_url():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please ad your remote database url in postgres render to .env")

    if "sslmode" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"
    return database_url


load_dotenv()

# Claude API model IDs. Sampling parameters are omitted: these models
# reject non-default temperature, top_p, and top_k. Thinking stays
# adaptive, and effort controls how much each model thinks.
HAIKU_MODEL = "claude-haiku-5-5"
SONNET_MODEL = "claude-sonnet-5-5"
OPUS_MODEL = "claude-opus-5-5"
GROQ_FALLBACK_MODEL = "openai/gpt-oss-120b"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not ANTHROPIC_API_KEY and not GROQ_API_KEY:
    raise ValueError(
        "ANTHROPIC_API_KEY or GROQ_API_KEY is required. "
        "Add ANTHROPIC_API_KEY for Claude. GROQ_API_KEY keeps the Groq fallback."
    )


def _claude(model: str, max_tokens: int, effort: str) -> ChatAnthropic:
    return ChatAnthropic(
        api_key=ANTHROPIC_API_KEY,
        model=model,
        max_tokens=max_tokens,
        output_config={"effort": effort},
    )


# Haiku extracts the flight fields. Opus plans the trip. Sonnet writes
# the brief the user reads. Groq is the same model as before, and it
# runs when Claude is unset or a Claude call fails.
flight_llm = (
    _claude(HAIKU_MODEL, max_tokens=4096, effort="low")
    if ANTHROPIC_API_KEY
    else None
)
itinerary_llm = (
    _claude(OPUS_MODEL, max_tokens=16000, effort="medium")
    if ANTHROPIC_API_KEY
    else None
)
final_llm = (
    _claude(SONNET_MODEL, max_tokens=16000, effort="high")
    if ANTHROPIC_API_KEY
    else None
)
groq_llm = (
    ChatGroq(api_key=GROQ_API_KEY, model=GROQ_FALLBACK_MODEL)
    if GROQ_API_KEY
    else None
)

if flight_llm is None:
    print("ANTHROPIC_API_KEY is not set. Using Groq until it is added.")

flight_extractor = (
    flight_llm.with_structured_output(FlightSearchParams, method="json_schema")
    if flight_llm is not None
    else None
)
groq_extractor = (
    groq_llm.with_structured_output(FlightSearchParams)
    if groq_llm is not None
    else None
)


# 5-minute prompt cache. The breakpoint sits on the stable system text.
# Claude caches a prefix only at 512 tokens or more, and a shorter prefix
# is billed as a normal request.
PROMPT_CACHE = {"type": "ephemeral"}

PLANNER_INSTRUCTIONS = """You are an expert travel planner for Skylane.

Write practical, budget-aware plans that a traveler can follow. Use only the trip facts in the user message. Do not invent flights, hotels, prices, or times that are not in those facts. When a fact is missing, say so in a few words and continue. Use the same place names, dates, airlines, and hotel names that appear in the user message.

When the user message asks for the itinerary, return only the day-by-day plan. Start each day with **Day 1: title**. Keep each day practical, in time order, and easy to follow. Do not add the other sections.

When the user message asks for the final travel brief, write Markdown with these headings, in this order. Each heading is on its own line, written exactly like this:

## Trip Summary
## Flight Information
## Hotel Suggestions
## Day-by-Day Itinerary
## Estimated Budget
## Final Recommendations

Rules for the final brief:
- Leave a blank line between sections.
- In Trip Summary, state where the traveler is going, the dates if known, and the kind of trip in a few sentences.
- In Flight Information, give each flight its own block. Use one line each for Airline, From, To, Departs, and Arrives.
- In Hotel Suggestions, use one bullet per hotel with the name, the area, and why it fits.
- In Day-by-Day Itinerary, start each day with **Day 1: title**.
- In Estimated Budget, use one line per cost and end with a total line. Keep the costs consistent with the flights, hotels, and days above.
- In Final Recommendations, give a short list of what to book, what to skip, and what to confirm before departure.
- Say each fact once. Do not paste raw search data, and do not add any other heading.
"""


def cached_system(text: str) -> SystemMessage:
    return SystemMessage(
        content=[
            {
                "type": "text",
                "text": text,
                "cache_control": PROMPT_CACHE,
            }
        ]
    )


def plain_messages(messages):
    """Drop Anthropic cache markers so the Groq fallback can read the same prompt."""
    converted = []
    for message in messages:
        content = message.content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            content = "\n".join(part for part in parts if part)
        converted.append(message.__class__(content=content))
    return converted


def _fallback_notice(step: str, exc: Exception) -> None:
    print(
        f"Anthropic {step} failed ({exc.__class__.__name__}). "
        "Falling back to Groq."
    )


def extract_flight_params(messages):
    if flight_extractor is not None:
        try:
            return flight_extractor.invoke(messages)
        except Exception as exc:
            if groq_extractor is None:
                raise
            _fallback_notice("flight extraction", exc)
    return groq_extractor.invoke(plain_messages(messages))


def invoke_llm(primary, messages, step: str):
    if primary is not None:
        try:
            return primary.invoke(messages)
        except Exception as exc:
            if groq_llm is None:
                raise
            _fallback_notice(step, exc)
    return groq_llm.invoke(plain_messages(messages))


def message_text(message) -> str:
    text = getattr(message, "text", None)
    if text is not None and str(text).strip():
        return str(text).strip()
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
    rendered = "\n".join(part for part in parts if part.strip())
    return rendered.strip() or str(content).strip()


# ===========================
# State
# ===========================


class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    flight_results: str
    hotel_results: str
    itinerary: str
    llm_calls: int


def flight_agent(state: TravelState):
    query = state["user_query"]

    # Step 1: Extract structured flight requirements
    today = datetime.now().astimezone().date().isoformat()

    params = extract_flight_params([
        cached_system(f"""
You are a flight search requirement extractor.

Today's date is {today}.

Extract the departure location, destination, and departure date
from the user's travel request.

Rules:
- Return the actual locations mentioned by the user.
- Do not invent an origin, destination, or date.
- Resolve relative dates such as "tomorrow" using today's date.
- Return departure_date as YYYY-MM-DD.
- If no departure date is specified, return null.
- Ignore hotel, party, sightseeing, and budget requirements
  unless they clarify the flight search.
"""),
        HumanMessage(content=query)
    ])

    # Step 2: Resolve locations to IATA airport codes
    origin_iata = resolve_location(params.origin)
    destination_iata = resolve_location(params.destination)

    # Step 3: Handle unresolved locations without crashing the graph
    if not origin_iata or not destination_iata:
        missing = []

        if not origin_iata:
            missing.append(f"origin '{params.origin}'")

        if not destination_iata:
            missing.append(f"destination '{params.destination}'")

        return {
            "flight_results": [],
            "messages": [
                AIMessage(
                    content=(
                        "I couldn't resolve the "
                        + " and ".join(missing)
                        + " to an airport. Please clarify the location."
                    )
                )
            ],
            "llm_calls": state.get("llm_calls", 0) + 1
        }

    # Step 4: Call the flight search. A refused lookup must not stop the trip.
    note = ""
    try:
        flight_data, note = search_flights(
            origin=origin_iata,
            destination=destination_iata,
            departure_date=params.departure_date,
            limit=20
        )
    except (RuntimeError, ValueError) as exc:
        flight_data = []
        note = str(exc)

    if note and flight_data:
        flight_results = note + "\n" + flights_for_prompt(flight_data)
    elif note:
        flight_results = note
    else:
        flight_results = flight_data

    if flight_data and not note:
        message = f"Flight search completed for {origin_iata} to {destination_iata}."
    else:
        message = note or f"No flights found for {origin_iata} to {destination_iata}."

    # Step 5: Return results to the LangGraph state
    return {
        "flight_results": flight_results,
        "messages": [
            AIMessage(content=message)
        ],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


def flights_for_prompt(flights) -> str:
    if not flights:
        return "No flights found."
    if isinstance(flights, str):
        text = flights.strip()
        return text or "No flights found."
    if not isinstance(flights, list):
        return str(flights)

    lines = []
    for raw in flights[:6]:
        if not isinstance(raw, dict):
            lines.append(f"- {raw}")
            continue

        flight = raw
        if isinstance(raw.get("departure"), dict) or isinstance(raw.get("airline"), dict):
            try:
                flight = format_flight(raw)
            except (AttributeError, TypeError):
                flight = raw

        airline = flight.get("airline") or "Unknown airline"
        number = flight.get("flight_number") or ""
        date = flight.get("flight_date") or ""
        origin = " ".join(
            part for part in (flight.get("origin"), flight.get("origin_airport")) if part
        )
        destination = " ".join(
            part for part in (flight.get("destination"), flight.get("destination_airport")) if part
        )
        lines.append(
            f"- {airline} {number} {date}: "
            f"{origin or 'origin unknown'} departs {flight.get('departure_time') or 'unscheduled'}; "
            f"{destination or 'destination unknown'} arrives {flight.get('arrival_time') or 'unscheduled'}"
        )

    return "\n".join(lines) if lines else "No flights found."


def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    hotel_results = tavily_search(query)

    return {
        "hotel_results": hotel_results,
        "messages": [
            AIMessage(content="Hotel details fetched.")
        ],
        "llm_calls": state.get("llm_calls", 0)+1
    }


def itinerary_agent(state: TravelState):
    prompt = f"""Write the itinerary.

User Query:
{state['user_query']}

Flight Details:
{flights_for_prompt(state['flight_results'])}

Hotel Details:
{state['hotel_results']}
"""

    response = invoke_llm(
        itinerary_llm,
        [
            cached_system(PLANNER_INSTRUCTIONS),
            HumanMessage(content=prompt),
        ],
        "itinerary",
    )

    return {
        "itinerary": message_text(response),
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


def final_agent(state: TravelState):
    final_prompt = f"""Write the final travel brief.

User Request:
{state['user_query']}

Flights:
{flights_for_prompt(state['flight_results'])}

Hotels:
{state['hotel_results']}

Itinerary:
{state['itinerary']}
"""
    response = invoke_llm(
        final_llm,
        [
            cached_system(PLANNER_INSTRUCTIONS),
            HumanMessage(content=final_prompt),
        ],
        "final brief",
    )

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0)+1
    }


# ========================
# Build the Graph
# ========================

graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("itinerary_agent", itinerary_agent)
graph.add_node("final_agent", final_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge("flight_agent", "hotel_agent")
graph.add_edge("hotel_agent", "itinerary_agent")
graph.add_edge("itinerary_agent", "final_agent")
graph.add_edge("final_agent", END)


DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)


# =====================
# function for FastAPI
# =====================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {"thread_id": thread_id}
    }

    result = travel_graph.invoke(
        {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "user_query": user_input,
            "flight_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0
        },
        config=config
    )

    final_answer = message_text(result["messages"][-1])

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "itinerary": result.get("itinerary", ""),
        "llm_calls": result.get("llm_calls",0),
    }


if __name__ == "__main__":

    user_input = input("Enter travel request: ")

    response = run_travel_agent(
        user_input=user_input,
        thread_id="test"
    )
    print(response["answer"])
