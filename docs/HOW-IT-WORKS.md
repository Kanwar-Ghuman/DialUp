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
  │  │   status     │    └───────┬────────┘    └───────┬────────┘ │
  │  │ Notifier     │◀───────────┼─────────────────────┘          │
  │  └──────────────┘            │ live events                    │
  │                              ▼                                │
  │                     web/live (projector)    mock_sites/bus    │
  └──────────────────────────────────────────────────────────────┘
```

| Module | Job |
| --- | --- |
| `telephony/routes.py` | Twilio endpoints. Turns calls and texts into tasks and answers. |
| `telephony/notifier.py` | Reaches the caller: outbound call for voice tasks, text for SMS tasks. |
| `telephony/twiml.py` | Builds TwiML for ConversationRelay and SMS replies. |
| `telephony/security.py` | Optional `X-Twilio-Signature` check. |
| `agent/runner.py` | Runs each task in the background. Claude picks a tool, the browser runs it, the guard checks. |
| `agent/tools.py` | Tool schemas for Claude and the Playwright actions behind them. |
| `agent/guards.py` | Supervisor. Hard limits plus loop and stuck detection. |
| `agent/prompts.py` | System prompt and supervisor messages. |
| `tasks/store.py` | SQLite tables for tasks and events. Survives restarts. |
| `tasks/journal.py` | Records every event: saves it, prints it, pushes it to the live view. |
| `tasks/inbox.py` | Routes the caller's answer back to the task that asked. |
| `web/live.py` | Live view at `/live`, fed by Server-Sent Events. |
| `mock_sites/bus.py` | BusBook, a predictable site for the demo. |
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
2. ConversationRelay sends the caller's speech to `/ws` as text. The server creates a task, starts the runner, says "I'll call you back," and hangs up.
3. The runner loops: Claude picks a tool, the browser runs it, the guard checks the run.
4. `ask_user`: the Inbox registers a waiting slot, then the Notifier calls the caller (`mode=ask`). Their answer arrives at `/ws` and the Inbox hands it to the waiting task.
5. On finish, give up or stop, the Notifier places the result call (`mode=result`) with a status callback.
6. If nobody answers the result call, `/twilio/status` gets `no-answer` and retries once after 30 seconds.

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
| Same action repeated | 3 times in the last 8 | Warn, then stop if it happens again |
| Clicks with no page change | 3 in a row | Warn, then stop if it happens again |

A warning is sent to Claude as a supervisor message: change approach or give up. Every stop still ends with a callback that explains what happened.

## ConversationRelay messages

From Twilio: `setup` (with our `customParameters`), `prompt` (`voicePrompt` holds the caller's words), `error`.

To Twilio: `{"type": "text", "token": "...", "last": true}` to speak, `{"type": "end"}` to hang up.

## Limits (hackathon scope)

- One server process. Tasks that are mid-run when the server restarts get marked failed, since their browser is gone.
- The agent's tools are general, but the prompt only points it at the mock bus site. Add more sites in `agent/prompts.py`.
