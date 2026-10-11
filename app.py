import asyncio
from pathlib import Path
import traceback
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator


from backend import run_travel_agent

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="AI travel planner",
    description = "Langgraph Multi-Agent Travel.",
    version="1.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR/"static")),
    name="static"
)

template = Jinja2Templates(
    directory=str(BASE_DIR/"templates")
)


class TravelRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, max_length=80)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Tell Skylane where you want to go.")
        return cleaned

    @field_validator("thread_id")
    @classmethod
    def clean_thread(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return template.TemplateResponse(request, "index.html")


@app.post("/api/travel")
async def travel(body: TravelRequest):
    try:
        return await asyncio.to_thread(
            run_travel_agent,
            body.query,
            body.thread_id,
        )
    except Exception:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "error": "Skylane could not finish this trip. Check the server log and try again."
            },
        )


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
