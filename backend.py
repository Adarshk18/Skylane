import operator
from tools.flight_tool import format_flight, resolve_location, search_flights
from tools.tavily_tool import tavily_search
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


GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is missing. Please add your groq api key to .env")


# ===========================
# LLM
# ===========================

llm = ChatGroq(
    api_key=GROQ_API_KEY,
    model="openai/gpt-oss-120b",
)

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
    extractor = llm.with_structured_output(FlightSearchParams)

    today = datetime.now().astimezone().date().isoformat()

    params = extractor.invoke([
        SystemMessage(content=f"""
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
    prompt = f""""Create a complete travel itinerary.

    User Query: 
    {state['user_query']}

    Flight Details:
    {flights_for_prompt(state['flight_results'])}

    Hotel Details:
    {state['hotel_results']}

    Make the itinerary practical, budget-aware, and easy to follow.
    """

    response = llm.invoke(
        [SystemMessage(content="You are an expert travel planner."),
         HumanMessage(content=prompt)
         ])

    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }


def final_agent(state: TravelState):
    final_prompt = f"""
    Generate the final travel response  for the user.

    User Request:
    {state['user_query']}

Flights:
{flights_for_prompt(state['flight_results'])}

Hotels:
{state['hotel_results']}

Itinerary:
{state['itinerary']}

Write the answer in Markdown with these headings, in this order.
Each heading is on its own line, written exactly like this:

## Trip Summary
## Flight Information
## Hotel Suggestions
## Day-by-Day Itinerary
## Estimated Budget
## Final Recommendations

Rules:
- Leave a blank line between sections.
- In Flight Information, give each flight its own block. Use one line each for Airline, From, To, Departs, and Arrives.
- In Hotel Suggestions, use one bullet per hotel with the name, the area, and why it fits.
- In Day-by-Day Itinerary, start each day with **Day 1: title**.
- In Estimated Budget, use one line per cost and end with a total line.
- Say each fact once. Do not paste raw search data, and do not add any other heading.
    
"""
    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=final_prompt)
    ])

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

    final_answer = result['messages'][-1].content

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
