# Dial-Up

The internet in a phone call.

3.1 billion people live under mobile internet coverage but don't use it. Nearly all of them can make a phone call.

With Dial-Up, you call a number, say what you need done, and hang up. "Find the cheapest bus to the city tomorrow and hold me a seat."

An AI agent does the task in a real browser. If it needs something only you know, like your name, it calls and asks. When it's done, it calls back with the result. If the task is impossible, it calls back and tells you why.

No app, no screen, no data plan. Any phone, in English or Chinese. Works over SMS too.

## Tracks

- **Primary:** Track 4, AI-Powered Consumer Products for 1 Billion People
- **Secondary:** Track 2, No App (users never look at a screen)

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
│   │   ├── guards.py         supervisor: limits, loop detection
│   │   └── prompts.py
│   ├── tasks/              state
│   │   ├── models.py         Task, Status, Channel
│   │   ├── store.py          SQLite (survives restarts)
│   │   ├── journal.py        event log + live event bus
│   │   └── inbox.py          routes answers back to the asking task
│   ├── web/live.py         live view for the projector
│   └── mock_sites/bus.py   demo bus site
├── scripts/smoke_test.py   offline end-to-end test
├── docs/                   setup, architecture, demo, build plan
└── .cursor/rules/          Cursor rules
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env              # fill it in
python scripts/smoke_test.py      # offline check, no keys used
ngrok http 8000                   # second terminal
uvicorn dialup.app:app --port 8000
```

Then open http://localhost:8000/live and call your Twilio number. Full steps are in `docs/SETUP.md`.

## Stack

Twilio ConversationRelay (speech-to-text and text-to-speech), FastAPI, Claude tool use, Playwright, SQLite, Server-Sent Events.
# DialUp
