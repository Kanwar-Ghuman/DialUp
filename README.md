# Dial-Up

The internet in a phone call.

3.1 billion people live within mobile internet coverage but don't use it (GSMA). Most of them can make a phone call.

With Dial-Up, you call a number, say what you need done, and hang up. "Find the cheapest bus to the city tomorrow and hold me a seat."

An AI agent does the task in a real browser. If it needs something only you know, like your name, it calls and asks. When it's done, it calls back with the result. If the task is impossible, it calls back and tells you why.

No app, no screen, no data plan. Any phone, in English or Chinese. Works over SMS too.

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
| No answer | Two unanswered calls to the caller end the task politely |

Every ending (done, gave up, stopped, crashed) still calls the caller back with a spoken explanation.

**Guardrails live in code, not just the prompt** (`agent/guardrails.py`):

- Clicks like "Hold", "Book", "Pay" are blocked until the caller says yes on a `confirm` call.
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
│   │   ├── notifier.py       outbound calls and texts
│   │   ├── twiml.py          TwiML builders
│   │   └── security.py       optional Twilio signature check
│   ├── agent/              the AI worker
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
│   └── mock_sites/bus.py   demo bus site
├── scripts/smoke_test.py   offline end-to-end test
├── tests/                  unit tests (supervisor, guardrails)
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
ngrok http 8000                   # second terminal
uvicorn dialup.app:app --port 8000
```

Then open http://localhost:8000/live and call your Twilio number. Full steps are in `docs/SETUP.md`.

## Stack

Twilio ConversationRelay (speech-to-text and text-to-speech), FastAPI, Claude tool use, Playwright, SQLite, Server-Sent Events.

## How we used AI coding tools

- **Kanwar** built the server, telephony, task store, live view and mock site in Cursor, with a project rules file (`.cursor/rules/dial-up.mdc`) that gives the assistant the architecture and coding rules on every change. _Kanwar: add anything distinctive here._
- **Sirui** used Claude to build the supervisor's dollar budget, the code-level guardrails, the confirm flow and the tests, first as a standalone prototype and then ported into this codebase in small, separately tested commits.
- **What we did differently:** we treated AI output as untrusted until it ran. Every change was checked with the offline smoke test and real model runs. That caught a budget cap that overshot (now predictive) and a booking click the prompt alone didn't stop (now blocked in code).

