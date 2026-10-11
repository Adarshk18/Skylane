const SECTIONS = [
  { title: "Trip summary", match: "trip summary" },
  { title: "Flight information", match: "flight information" },
  { title: "Hotel suggestions", match: "hotel suggestions" },
  { title: "Day-by-day itinerary", match: "day by day itinerary" },
  { title: "Estimated budget", match: "estimated budget" },
  { title: "Final recommendations", match: "final recommendations" },
];

const NOTES = [
  "Checking flights.",
  "Looking up places to stay.",
  "Building the day-by-day plan.",
  "Putting the trip together.",
];

const TAB_FOR_TITLE = {
  "Trip summary": "summary",
  "Flight information": "flights",
  "Hotel suggestions": "stays",
  "Day-by-day itinerary": "itinerary",
  "Estimated budget": "budget",
  "Final recommendations": "tips",
};

const SAMPLE_ANSWER = `1. Trip Summary
A four-day Lisbon trip, leaving from Delhi next month. The pace is slow: one neighborhood each afternoon, with food as the main plan.

2. Flight Information
Airline: IndiGo
From: Delhi (DEL)
To: Lisbon (LIS)
Departs: 02:10
Arrives: 09:40

3. Hotel Suggestions
Two or three mid-range stays in walkable neighborhoods, with a short note on why each one fits the trip.

4. Day-by-Day Itinerary
Day 1 is for arrival and a short walk. The next days keep one main outing and an unhurried afternoon.

5. Estimated Budget
A live brief separates flights, lodging, food, and local transit, then gives a trip total.

6. Final Recommendations
Book the flight first, keep one day loose, and stay somewhere you can walk to dinner.`;

const form = document.querySelector("#trip-form");
const queryInput = document.querySelector("#query");
const submitButton = document.querySelector("#submit");
const submitLabel = document.querySelector("#submit-label");
const errorEl = document.querySelector("#form-error");
const emptyEl = document.querySelector("#brief-empty");
const loadingEl = document.querySelector("#brief-loading");
const resultEl = document.querySelector("#brief-result");
const resultKicker = document.querySelector("#result-kicker");
const resultTitle = document.querySelector("#result-title");
const resultQuery = document.querySelector("#result-query");
const resultBody = document.querySelector("#result-body");
const resultMeta = document.querySelector("#result-meta");
const loadingNote = document.querySelector("#loading-note");
const steps = [...document.querySelectorAll("#steps li")];
const brief = document.querySelector("#brief");
const planTabs = document.querySelector("#plan-tabs");

const PLAN_ROUTE = "/api/travel";

let threadId = null;
let progressTimer = null;

document.querySelectorAll(".sample").forEach((button) => {
  button.addEventListener("click", () => {
    queryInput.value = button.dataset.query;
    queryInput.focus();
  });
});

document.querySelector("#show-sample").addEventListener("click", showSample);
document.querySelector("#new-trip").addEventListener("click", startNewTrip);
form.addEventListener("submit", onSubmit);
planTabs.addEventListener("click", (event) => {
  const button = event.target.closest(".plan-tab");
  if (!button) return;
  applyTab(button.dataset.tab);
});

if (new URLSearchParams(location.search).get("sample") === "1") {
  showSample();
}

function showSample() {
  renderResult({
    query: "Four days in Lisbon next month, leaving from Delhi. Mid-range hotels, food, and a slow afternoon in each neighborhood.",
    answer: SAMPLE_ANSWER,
    sample: true,
  });
}

function startNewTrip() {
  threadId = null;
  queryInput.value = "";
  hideError();
  showPanel("empty");
  setBusy(false);
  queryInput.focus();
}

async function onSubmit(event) {
  event.preventDefault();
  hideError();

  const query = queryInput.value.trim();
  if (!query) {
    showError("Tell Skylane where you want to go.");
    return;
  }

  setBusy(true);
  showPanel("loading");
  startProgress();

  try {
    const data = await requestPlan(query, threadId);
    threadId = data.thread_id || threadId;
    renderResult({
      query,
      answer: data.answer,
      llm_calls: data.llm_calls,
    });
  } catch (error) {
    showPanel(resultBody.childElementCount ? "result" : "empty");
    showError(error.message || "Skylane could not plan this trip.");
  } finally {
    stopProgress();
    setBusy(false);
  }
}

async function requestPlan(query, currentThreadId) {
  const payload = { query };
  if (currentThreadId) {
    payload.thread_id = currentThreadId;
  }

  const response = await fetch(PLAN_ROUTE, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(errorMessage(data));
  }
  return data;
}

function answerText(answer) {
  let text = "";
  if (typeof answer === "string") text = answer.trim();
  else if (Array.isArray(answer)) {
    text = answer
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part.text === "string") return part.text;
        return "";
      })
      .join("\n")
      .trim();
  }
  return text.replace(/^```(?:markdown|md)?\s*/i, "").replace(/\s*```$/, "").trim();
}

function renderResult(data) {
  const answer = answerText(data.answer);
  resultKicker.textContent = data.sample ? "Sample" : "Trip";
  resultTitle.textContent = data.sample ? "Sample itinerary" : "Your plan";
  resultQuery.textContent = data.query || "";
  resultBody.replaceChildren();

  if (data.sample) {
    const flag = document.createElement("p");
    flag.className = "sample-flag";
    flag.textContent = "This is a sample plan, not a live search.";
    resultBody.append(flag);
  }

  if (!answer) {
    const empty = document.createElement("p");
    empty.textContent = "The desk returned no brief. Try the request again with a city, a date, and a departure city.";
    resultBody.append(empty);
  } else {
    appendAnswer(resultBody, answer);
  }

  if (data.sample) {
    resultMeta.textContent = "Sample plan. Search to build a real one.";
  } else if (threadId) {
    resultMeta.textContent = "Update the search to change this trip.";
  } else {
    resultMeta.textContent = "";
  }

  const hasTabs = resultBody.querySelector(".section[data-tab]");
  planTabs.hidden = !hasTabs;
  if (hasTabs) applyTab("all");
  showPanel("result");
}

function appendAnswer(container, answer) {
  const chunks = splitAnswer(answer);
  const titled = chunks.some((chunk) => chunk.title);

  chunks.forEach((chunk) => {
    const section = document.createElement("section");
    section.className = chunk.title || !titled ? "section" : "section section-preamble";
    section.dataset.tab = TAB_FOR_TITLE[chunk.title] || "summary";
    if (chunk.title) {
      const heading = document.createElement("h3");
      heading.textContent = chunk.title;
      section.append(heading);
    }
    const prose = document.createElement("div");
    prose.className = "prose";
    prose.innerHTML = renderBlocks(chunk.body);
    section.append(prose);
    container.append(section);
  });
}

function splitAnswer(answer) {
  const chunks = [];
  let current = null;

  const push = (chunk) => {
    if (!chunk) return;
    const body = chunk.lines.join("\n").trim();
    if (!chunk.title && !body) return;
    chunks.push({ title: chunk.title, body });
  };

  answer.replaceAll("\r\n", "\n").split("\n").forEach((line) => {
    const found = matchSection(line);
    if (found) {
      push(current);
      current = { title: found.title, lines: found.rest ? [found.rest] : [] };
      return;
    }
    if (!current) current = { title: null, lines: [] };
    current.lines.push(line);
  });

  push(current);
  return chunks.length ? chunks : [{ title: null, body: answer }];
}

function matchSection(line) {
  let text = line.trim().replace(/^#{1,6}\s+/, "");
  text = text.replace(/^\*\*(.+)\*\*$/, "$1").replace(/^__(.+)__$/, "$1");
  text = text.replace(/^\d+[\.\)]\s*/, "");
  text = text.replace(/^\*\*(.+)\*\*$/, "$1").trim();
  if (!text) return null;

  const normalized = text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  for (const section of SECTIONS) {
    const words = section.match.split(" ").map(escapeRegExp).join("[^a-z0-9]+");
    const pattern = new RegExp(`^${words}(?:[^a-z0-9]+(.*))?$`, "i");
    if (normalized === section.match) {
      return { title: section.title, rest: "" };
    }
    const found = text.match(pattern);
    if (!found) continue;
    const rest = (found[1] || "").replace(/^[\s:–—-]+/, "").trim();
    if (rest && rest.length > 80) continue;
    return { title: section.title, rest };
  }
  return null;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderBlocks(text) {
  const parts = [];
  let list = null;
  let paragraph = [];
  let facts = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    parts.push(`<p>${inline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!list) return;
    const items = list.items.map((item) => `<li>${inline(item)}</li>`).join("");
    parts.push(`<${list.type}>${items}</${list.type}>`);
    list = null;
  };

  const flushFacts = () => {
    if (!facts.length) return;
    const rows = facts
      .map((fact) => `<dt>${inline(fact.label)}</dt><dd>${inline(fact.value)}</dd>`)
      .join("");
    parts.push(`<dl class="facts">${rows}</dl>`);
    facts = [];
  };

  text.split("\n").forEach((raw) => {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      flushList();
      flushFacts();
      return;
    }

    const subhead = subheadText(line);
    if (subhead) {
      flushParagraph();
      flushList();
      flushFacts();
      parts.push(`<h4>${inline(subhead)}</h4>`);
      return;
    }

    const fact = factParts(line);
    if (fact) {
      flushParagraph();
      flushList();
      facts.push(fact);
      return;
    }

    const bullet = line.match(/^[-*•]\s+(.+)$/);
    const numbered = line.match(/^\d+[\.\)]\s+(.+)$/);
    if (bullet || numbered) {
      flushParagraph();
      flushFacts();
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        flushList();
        list = { type, items: [] };
      }
      list.items.push((bullet || numbered)[1]);
      return;
    }

    flushList();
    flushFacts();
    paragraph.push(line.replace(/^\*\*(.+)\*\*$/, "$1"));
  });

  flushParagraph();
  flushList();
  flushFacts();
  return parts.join("") || `<p>${inline(text)}</p>`;
}

function subheadText(line) {
  let plain = line.trim().replace(/^#{1,6}\s+/, "");
  const bold = plain.match(/^\*\*(.+)\*\*$/);
  if (bold) plain = bold[1].trim();
  plain = plain.replace(/\*\*/g, "").trim();
  if (/^day\s+\d+\b/i.test(plain) && plain.length < 90) return plain;
  return null;
}

function factParts(line) {
  const plain = line.trim().replace(/^\*\*(.+)\*\*$/, "$1");
  const match = plain.match(/^([^:]{2,28}):\s+(\S.*)$/);
  if (!match) return null;
  const label = match[1].replace(/\*/g, "").trim();
  if (/^day\s+\d+/i.test(label)) return null;
  if (label.split(/\s+/).length > 4) return null;
  return { label, value: match[2].trim() };
}

function inline(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>');
  return html;
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function errorMessage(data) {
  if (typeof data.error === "string" && data.error.trim()) return data.error;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    const message = data.detail.map((item) => item.msg).filter(Boolean).join(" ");
    if (message) return message.replace(/^Value error,\s*/i, "");
  }
  return "Skylane could not plan this trip.";
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
}

function hideError() {
  errorEl.hidden = true;
  errorEl.textContent = "";
}

function showPanel(name) {
  emptyEl.hidden = name !== "empty";
  loadingEl.hidden = name !== "loading";
  resultEl.hidden = name !== "result";
  if (name !== "result") planTabs.hidden = true;
  brief.setAttribute("aria-busy", name === "loading" ? "true" : "false");
}

function applyTab(tabId) {
  planTabs.querySelectorAll(".plan-tab").forEach((button) => {
    const on = button.dataset.tab === tabId;
    button.classList.toggle("is-on", on);
    button.setAttribute("aria-selected", on ? "true" : "false");
  });
  resultBody.querySelectorAll(".section").forEach((section) => {
    section.hidden = tabId !== "all" && section.dataset.tab !== tabId;
  });
}

function setBusy(busy) {
  form.classList.toggle("is-busy", busy);
  submitButton.disabled = busy;
  queryInput.disabled = busy;
  document.querySelectorAll(".sample").forEach((button) => {
    button.disabled = busy;
  });
  submitLabel.textContent = busy
    ? "Searching"
    : threadId
      ? "Update trip"
      : "Plan trip";
}

function startProgress() {
  stopProgress();
  let index = 0;
  paintStep(index);
  progressTimer = window.setInterval(() => {
    index = Math.min(index + 1, NOTES.length - 1);
    paintStep(index);
  }, 8000);
}

function paintStep(index) {
  steps.forEach((step, stepIndex) => {
    step.classList.toggle("is-done", stepIndex < index);
    step.classList.toggle("is-active", stepIndex === index);
  });
  loadingNote.textContent = NOTES[index];
}

function stopProgress() {
  if (progressTimer) {
    window.clearInterval(progressTimer);
    progressTimer = null;
  }
}
