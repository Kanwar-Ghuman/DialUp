# How it works

## Architecture

```
  Any phone ── voice call or SMS ──┐
                                   ▼
  ┌──────────────────────────────────────────┐
  │ Twilio                                    │
  │   phone number, SMS                       │
  │   ConversationRelay (speech <-> text)     │
  └──────────────────────────────────────────┘
                 │ webhooks + WebSocket (text only)
                 ▼  via ngrok
  ┌──────────────────────────────────────────────────────────────┐
  │ FastAPI server (dialup/)                                      │
  │                                                               │
  │  telephony/          tasks/                agent/             │
  │  ┌──────────────┐    ┌────────────────┐    ┌────────────────┐ │
  │  │ /voice       │──▶ │ Store (SQLite) │ ◀──│ Runner         │ │
  │  │ /ws (relay)  │    │ Journal        │    │  Claude: think │ │
  │  │ /sms         │◀── │ Inbox          │ ──▶│  Browser: act  │ │
  │  │ /twilio/     │    │ EventBus       │    │  Guard: watch  │ │
  │  │   status     │    └───────┬────────┘    │  Guardrails    │ │
  │  │ Notifier     │◀───────────┼─────────────└───────┬────────┘ │
  │  │ Lines        │            │ live events         │ intake   │
  │  └──────────────┘            ▼                     ▼          │
  │                     web/live (projector)   mock_sites/bus,    │
  │                                            mock_sites/clinic, │
  │                                            the real web       │
  └──────────────────────────────────────────────────────────────┘
```

| Module | Job |
| --- | --- |
| `telephony/routes.py` | Twilio endpoints. Turns calls and texts into tasks and answers. |
| `telephony/notifier.py` | Reaches the caller: outbound question and result calls for voice tasks, texts for SMS tasks. |
| `telephony/lines.py` | One line per caller: Dial-Up never rings someone who is already on a call with it, and a finished call's status can't affect the next one. |
| `telephony/twiml.py` | Builds TwiML for ConversationRelay and SMS replies. |
| `telephony/security.py` | Optional `X-Twilio-Signature` check. |
| `agent/intake.py` | During the first call, asks follow-up questions until the task has the details it needs (dates, names, date of birth for appointments). |
| `agent/runner.py` | Runs each task in the background. Claude picks a tool, the browser runs it, the guard checks. Handles `ask_user` and `confirm` calls. |
| `agent/tools.py` | Tool schemas for Claude and the Playwright actions behind them. |
| `agent/guards.py` | Supervisor. Hard limits, the predictive dollar budget, loop and stuck detection. |
| `agent/guardrails.py` | Safety rules in code: irreversible clicks need the caller's yes; never type passwords, card numbers or SSNs. |
| `agent/prompts.py` | System prompt and supervisor messages. |
| `tasks/store.py` | SQLite tables for tasks and events. Survives restarts. |
| `tasks/journal.py` | Records every event: saves it, prints it, pushes it to the live view. |
| `tasks/inbox.py` | Routes the caller's answer back to the task that asked. |
| `web/live.py` | Live view at `/live`, fed by Server-Sent Events. |
| `mock_sites/bus.py` | BusBook, a predictable bus site for the demo. |
| `mock_sites/clinic.py` | Harbor Community Clinic, a predictable appointment site for the demo. |
| `i18n.py` | Caller-facing phrases in English and Chinese. |
| `app.py` | Builds everything at startup and wires it together. |

## Task lifecycle

```
queued ──▶ running ──▶ done        agent called finish
              │  ▲  ──▶ gave_up     agent called give_up
              ▼  │  ──▶ stopped     guard stopped it
   waiting_on_caller ──▶ failed     crash, or server restarted mid-task
```

Every end state triggers a callback. A caller is never left waiting.

## Voice flow

1. Caller dials in. Twilio calls `POST /voice`, which plays the language menu. The keypress goes to `POST /voice/language`, which returns TwiML pointing at `/ws` with `mode=intake` and the chosen language's voice settings.
2. ConversationRelay sends the caller's speech to `/ws` as text. The server waits for a short pause (`SPEECH_PAUSE`) so a caller who stops mid-sentence isn't cut off. `intake.py` asks follow-up questions until the task is clear, then the server creates the task, starts the runner, reads the task back and hangs up.
3. The runner loops: Claude picks a tool, the browser runs it, the guard checks the run.
4. `ask_user`: the Inbox registers a waiting slot, then the Notifier calls the caller (`mode=ask`). Their answer arrives at `/ws` and the Inbox hands it to the waiting task.
5. `confirm`: same as `ask_user`, with "say yes or press 1, say no or press 2" added. Keypresses arrive as `dtmf` messages. Until the caller says yes, clicks like Book, Hold or Pay are blocked. An unclear answer is asked again.
6. Calls to one caller never overlap (`lines.py`). If a question call is busy or unanswered, it's retried; two unanswered calls end the task with a polite message.
7. On finish, give up or stop, the Notifier places the result call (`mode=result`) with a status callback. If nobody answers, `/twilio/status` gets `no-answer` and retries once after 30 seconds. `CALL_DELAY` can pace calls for a demo.

## SMS flow

Same runner. `POST /sms` creates the task. Questions and results go out as texts. If the caller has a task waiting on an answer, their next text goes to that task instead of starting a new one.

## Languages

Each task stores its language (`en` or `zh`). Everything downstream uses it:

| Piece | How language is used |
| --- | --- |
| `i18n.py` | Every fixed phrase the caller hears or reads, per language |
| `config.py` | ConversationRelay voice settings per language: TTS and speech-to-text provider, language code, voice. All overridable in `.env`. |
| `/voice/language` | Starts the conversation with the chosen language's voice |
| `agent/prompts.py` | Tells Claude which language to use when speaking. It still reads English websites. |
| `notifier.py` | Question and result calls use the task's language |
| `/sms` | Chinese characters in a text mean a Chinese task |

## The guard

The guard is what makes Dial-Up safe to leave alone.

| Check | Default | Action |
| --- | --- | --- |
| Steps | 25 | Stop |
| Time | 15 minutes | Stop |
| Tokens | 400,000 | Stop |
| Dollars | $0.50 (`COST_BUDGET`) | Stop **before** the next model call would cross it, with room left for the closing message |
| Calls to the caller | 4 per task; 2 unanswered | Further questions blocked; 2 unanswered ends the task |
| Same action repeated | 3 times in the last 8 | Warn, then stop if it happens again |
| Clicks with no page change | 3 in a row | Warn, then stop if it happens again |

A warning is sent to Claude as a supervisor message: change approach or give up. Every stop still ends with a callback; Claude writes a short summary of what it found before stopping (if that fails, a standard phrase is used).

Separate from the guard, `guardrails.py` blocks unsafe actions outright: an irreversible click without the caller's yes, typing into a password field, or typing anything that looks like a card number or SSN. Page text is treated as untrusted data in the prompt.

## ConversationRelay messages

From Twilio: `setup` (with our `customParameters`), `prompt` (`voicePrompt` holds the caller's words), `dtmf` (`digit`, a keypress; used to answer questions), `error`.

Our TwiML turns on `dtmfDetection`, so "press 1" works on question calls.

To Twilio: `{"type": "text", "token": "...", "last": true}` to speak, `{"type": "end"}` to hang up.

## Limits (hackathon scope)

- One server process. Tasks that are mid-run when the server restarts get marked failed, since their browser is gone.
- The agent's tools are general. The prompt points it at two demo sites (bus, clinic) for bookings and at the real web, through DuckDuckGo, for facts. Real booking sites usually need logins or payment, which the agent refuses on purpose.
- In-memory state (Inbox, Lines) means one server process. See "Scaling to a billion people" in the README.
