# Skylane
Multi Agent Travel Planner with LangGraph##C

uv init 

## Create Virtual env

uv venv

## Activate env
.venv\Scripts\activate

## Install the requirements
uv add -r requirements.txt

## Environment

Set these in `.env` and on Render. At least one model key is required.

- `ANTHROPIC_API_KEY` — Claude. Flight extraction uses `claude-haiku-5-5`, the itinerary uses `claude-opus-5-5`, and the final brief uses `claude-sonnet-5-5`.
- `GROQ_API_KEY` — fallback when Claude is unset or a Claude call fails. The fallback model stays `openai/gpt-oss-120b`.
- `DATABASE_URL` — Postgres connection string.
- `TAVILY_API_KEY` — hotel search.
- `AVIATIONSTACK_API_KEY` — flight search.

