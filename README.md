# Dial-Up

The internet in a phone call.

3.1 billion people live within mobile internet coverage but don't use it (GSMA). Most don't own a smartphone, and many don't own a phone at all. A voice call works from any phone: basic, shared or borrowed.

With Dial-Up, you call a number, say what you need done, and hang up. "Book me a flu shot at the clinic this week, in the morning."

It asks for anything it's missing before you hang up (like the patient's name). Then an AI agent does the task in a real browser. Before anything irreversible it calls you to confirm. When it's done, it calls back with the result. If the task is impossible, it calls back and tells you why.

No app, no screen, no data plan. English or Chinese, by voice or SMS.

**What it can do today:** book a clinic appointment or hold a bus seat on two demo sites, and look up facts (hours, prices, schedules) on the real web, reading the answer off a page it opened.

## Track

Track 4: AI-Powered Consumer Products for 1 Billion People.

## Knowing when to stop

The agent works alone for minutes at a time, so a supervisor (`agent/guards.py`) checks every step.
It uses measurable signals, not the agent's own opinion:

| Stop | Rule |
|---|---|
| Budget | Stops **before** the next model call would cross the per-task dollar cap (`COST_BUDGET`), leaving room for the closing message |
| Loop | Same action 3 times in the last 8: one warning, then a stop |
| No effect | Clicks that don't change the page, 3 in a row: one warning, then a stop |
| Hard limits | Steps, minutes and tokens, plus a hard timeout that can interrupt a hung step |
| No answer | Two unanswered calls to the caller end the task politely; at most 4 calls to the caller per task |

Every ending (done, gave up, stopped, crashed) still calls the caller back. A stopped task says what it found before stopping.

**Guardrails live in code, not just the prompt** (`agent/guardrails.py`):

- Clicks like "Hold", "Book", "Pay" are blocked until the caller says yes (or presses 1) on a `confirm` call. Answers that aren't a clear yes or no get asked again.
- Password fields, card numbers (checksum-verified) and SSN-shaped text are never typed.
- Web page text is treated as untrusted data, never instructions.

## Project layout

```
dial-up/
├── dialup/
│   ├── app.py              FastAPI app, startup wiring
│   ├── config.py           settings from .env, voice per language
│   ├── i18n.py             English and Chinese phrases
│   ├── services.py         shared objects container
│   ├── telephony/          everything Twilio
│   │   ├── routes.py         /voice, /ws, /sms, /twilio/status
│   │   ├── notifier.py       outbound question and result calls, texts
│   │   ├── lines.py          one line per caller: never rings someone already on a call
│   │   ├── twiml.py          TwiML builders
│   │   └── security.py       optional Twilio signature check
│   ├── agent/              the AI worker
│   │   ├── intake.py         live intake: asks for missing details before hanging up
│   │   ├── runner.py         background task loop
│   │   ├── tools.py          tool schemas + browser actions
│   │   ├── guards.py         supervisor: limits, budget, loop detection
│   │   ├── guardrails.py     hard safety rules: confirm before booking, no secrets
│   │   └── prompts.py
│   ├── tasks/              state
│   │   ├── models.py         Task, Status, Channel
│   │   ├── store.py          SQLite (survives restarts)
│   │   ├── journal.py        event log + live event bus
│   │   └── inbox.py          routes answers back to the asking task
│   ├── web/live.py         live view for the projector
│   └── mock_sites/         demo sites: bus.py (BusBook), clinic.py (Harbor Community Clinic)
├── scripts/
│   ├── smoke_test.py       offline end-to-end test (scripted model, fake caller)
│   └── try_agent.py        real Claude and browser, your terminal as the phone
├── tests/                  unit tests (supervisor, guardrails, phone lines)
├── docs/                   setup, architecture, demo
└── .cursor/rules/          Cursor rules
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env              # fill it in
python scripts/smoke_test.py      # offline end-to-end check, no keys used
python -m pytest tests -q         # unit tests
python scripts/try_agent.py "Book me a flu shot this week"   # real agent, no phone needed
ngrok http 8000                   # second terminal
uvicorn dialup.app:app --port 8000
```

Then open http://localhost:8000/live and call your Twilio number. Full steps are in `docs/SETUP.md`.

## Scaling to a billion people

This is a hackathon build: one server process, one Twilio number, two demo sites. What it takes to reach a billion people, and where each piece stands:

| Piece | Today | At scale |
|---|---|---|
| Reaching callers | One US number | Local or toll-free numbers per country through carrier partners, so calling costs the caller nothing. Dial-Up already calls the user back, which fits the "missed call, we call you" habit common in many markets. |
| Phones | Any phone that can call; SMS too | Same. No app, no data plan, no account. A shared or borrowed phone works. |
| Server | One process; in-memory inbox and phone lines; SQLite | Stateless web workers behind a queue, shared state in Redis/Postgres, a pool of browsers in their own workers. The modules already split this way: telephony, tasks, agent. |
| Cost | About 5 cents of model time for a typical task | Cheaper models for simple steps and caching shrink it. Paid by partners: telcos, NGOs, clinics and governments that want to reach people offline. |
| Languages | English and Chinese | Each language is one phrase file plus a voice config. Limited mainly by speech recognition quality per language. |
| Websites | Two demo sites plus read-only facts from the real web | Real sites often block bots or need logins. High-value services (clinics, benefits, transit) get direct partner integrations; the agent keeps the open web for lookups. |
| Safety | Confirm-in-code, budget, no secrets, injection-resistant prompt | Same rules, plus caller verification for sensitive tasks and audit logs per task (the journal already records every step). |

## Stack

Twilio ConversationRelay (speech-to-text and text-to-speech), FastAPI, Claude tool use, Playwright, SQLite, Server-Sent Events.

## How we used AI coding tools

- **Kanwar** built the server, telephony, task store, live view and mock site in Cursor, with a project rules file (`.cursor/rules/dial-up.mdc`) that gives the assistant the architecture and coding rules on every change. _Kanwar: add anything distinctive here._
- **Sirui** used Claude to build the supervisor's dollar budget, the code-level guardrails, the confirm flow and the tests, first as a standalone prototype and then ported into this codebase in small, separately tested commits.
- **What we did differently:** we treated AI output as untrusted until it ran. Every commit passes the offline smoke test, and the prototype was tested with real model runs. Those runs caught a budget cap that overshot its limit (now predictive) and two API issues before they reached the shared code.

