# Build plan (2:00 PM to 7:30 PM)

The code already works end to end offline. Today is about real phones, reliability and demo polish.

## Before 2:00 PM

- [ ] `python scripts/smoke_test.py` passes
- [ ] Twilio number bought, phones verified, ConversationRelay addendum on
- [ ] `.env` filled in, static ngrok domain claimed
- [ ] One inbound call works (you hear the greeting)

## 2:00 to 3:00: real phone loop

- [ ] Full voice test: intake, agent runs, question call, result call
- [ ] Full SMS test
- [ ] Chinese call test (press 2). If it fails, use the fallback table in `docs/SETUP.md`
- [ ] Fix anything using the table in `docs/SETUP.md`

## 3:00 to 4:30: reliability

- [ ] Run the bus task 5 times with real Claude. Note every failure in the live view.
- [ ] Tighten `dialup/agent/prompts.py` for anything that failed
- [ ] Test the impossible task
- [ ] Test ignoring the question call. It should still call back.
- [ ] Test ignoring the result call. It should retry once.

## 4:30 to 5:30: one stretch feature (split across teammates)

The modules are separate, so these can be built in parallel without merge conflicts:

- [ ] **Chinese demo polish** (`i18n.py`, `config.py`). Get the Chinese call sounding natural; tune voices in `.env`.
- [ ] **Second mock site** (new file in `mock_sites/`, one line in `agent/prompts.py`). For example an application status checker.
- [ ] **Live view polish** (`web/live.py`). Bigger fonts for the projector, a counter of tasks done.

## 5:30 to 6:30: demo prep

- [ ] Record the backup video
- [ ] One slide: "3.1 billion people" plus the architecture diagram from `docs/HOW-IT-WORKS.md`
- [ ] Practice `docs/DEMO.md` twice, out loud
- [ ] Set `VALIDATE_TWILIO=true` and make one test call

## 6:30 to 7:30: submit

- [ ] Write the submission (pitch from `README.md`)
- [ ] Push to GitHub with `.env` and `*.db` excluded
- [ ] Test one call 10 minutes before demos
