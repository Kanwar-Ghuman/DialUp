# Setup

This takes about 30 minutes. Do steps 1 to 6 before building starts at 2:00 PM.

## What you need

- Python 3.10 or newer
- A phone that can make and receive calls and texts
- A Twilio account (free trial works)
- An Anthropic API key with credits
- ngrok (free account)

## 1. Install the project and run the offline test

Do this first. It proves your machine is ready before you touch any accounts.

```bash
cd dial-up
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python scripts/smoke_test.py
```

The test starts the real server and drives it the way Twilio would, with a scripted model instead of Claude. It runs a voice booking, an SMS booking, an impossible task, and a stuck agent. It ends with `All checks passed.` It uses no API keys and costs nothing.

## 2. Create a Twilio account and buy a number

1. Sign up at https://www.twilio.com/try-twilio.
2. Go to **Phone Numbers > Manage > Buy a number**.
3. Pick a US number with **Voice** and **SMS**.
4. Copy the number in `+15551234567` format.
5. From the console home page, copy your **Account SID** and **Auth Token**.

## 3. Verify every phone you'll use

Trial accounts can only call and text verified numbers. Dial-Up calls the caller back, so this matters.

1. Go to **Phone Numbers > Manage > Verified Caller IDs**.
2. Add your phone and your teammates' phones.

Trial outbound calls start with a short Twilio message and ask the person to press a key. Press any key and the call continues. Upgrading with $20 removes this and looks much cleaner on stage.

## 4. Turn on ConversationRelay

1. Go to **Voice > Settings > General**.
2. Turn on **Predictive and Generative AI/ML Features Addendum**.

If you skip this, calls connect and drop right away.

## 5. Get an Anthropic API key

1. Go to https://console.anthropic.com, then **API Keys**.
2. Create a key and make sure the account has credits.

## 6. Start ngrok

```bash
ngrok http 8000
```

Copy the host from the `Forwarding` line, for example `abc123.ngrok-free.app`. Keep this terminal open.

The host changes every time ngrok restarts. Claim a free static domain in the ngrok dashboard and run `ngrok http --url=your-name.ngrok-free.app 8000` instead.

## 7. Fill in `.env`

```bash
cp .env.example .env
```

Fill in the five required values. `PUBLIC_HOST` is the ngrok host with no `https://`.

## 8. Run the server

```bash
uvicorn dialup.app:app --port 8000
```

You should see:

```
Dial-Up ready
  Twilio voice webhook  https://abc123.ngrok-free.app/voice
  Twilio SMS webhook    https://abc123.ngrok-free.app/sms
  Live view             http://localhost:8000/live
```

## 9. Point your Twilio number at the server

1. Go to **Phone Numbers > Manage > Active numbers** and click your number.
2. **Voice Configuration > A call comes in:** Webhook, `https://abc123.ngrok-free.app/voice`, HTTP POST.
3. **Messaging Configuration > A message comes in:** Webhook, `https://abc123.ngrok-free.app/sms`, HTTP POST.
4. Save.

## 10. Test with a real phone

Open http://localhost:8000/live on your laptop. Every step shows up there.

1. **Inbound call.** Call your number. You hear the language menu. Press 1, then you hear "Hi, this is Dial-Up."
2. **Full task.** Say "Find me the cheapest bus from San Diego to Los Angeles tomorrow and hold a seat," then hang up. Steps appear in the live view.
3. **Question call.** Your phone rings: "What name should the seat be under?" Say your name.
4. **Result call.** Your phone rings with the seat, price and code.
5. **SMS.** Text the same request to the number. Reply to the question by text.
6. **Impossible task.** Ask for "a bus to the moon." You get a callback explaining why not.
7. **Chinese.** Call, press 2, and ask in Chinese. See "Languages" below.

## 11. Before demos: lock it down (optional)

Set `VALIDATE_TWILIO=true` in `.env` and restart. Webhooks without a valid Twilio signature get rejected. Make one test call afterward to confirm it still works.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Call says "an application error has occurred" | Webhook URL wrong or server not running. Check the ngrok terminal for the request. |
| Call connects, then drops | ConversationRelay addendum off (step 4), or `PUBLIC_HOST` wrong. |
| `KeyError: 'TWILIO_SID'` on start | `.env` missing, or you ran `uvicorn` from a different folder. |
| No callback, error 21219 in Twilio logs | The phone isn't verified (step 3). |
| 403 on every webhook | `VALIDATE_TWILIO=true` but `PUBLIC_HOST` doesn't match the URL Twilio calls. Fix the host or turn validation off. |
| Live view shows `guard warning` a lot | The agent is struggling with a page. Read its steps, then tighten `dialup/agent/prompts.py`. |
| Result call cuts off mid-sentence | Raise `RESULT_HOLD` in `.env`. |
| Everything broke after restarting ngrok | New host. Update `.env`, restart the server, update both Twilio webhooks. |

Twilio call logs are under **Monitor > Logs > Calls**. Every failed call has an error code and a reason.

## Languages (English and Chinese)

Dial-Up supports English and Mandarin Chinese out of the box.

- **Calls:** callers hear "For English, press 1. 中文服务，请按 2。" If they press nothing, it uses `DEFAULT_LANGUAGE`.
- **Texts:** a text with Chinese characters gets Chinese replies.
- **Callbacks:** the agent's questions and results come back in the caller's language.

To skip the menu, set `LANGUAGES=en` or `LANGUAGES=zh`.

### Test a Chinese call first

Twilio's docs don't list every language code each speech provider accepts, so test Chinese as soon as English works:

1. Call, press 2, and say: "帮我找明天从圣地亚哥到洛杉矶最便宜的巴士，并帮我订一个座位".
2. Check that you hear the Chinese greeting and confirmation.
3. Check the live view: the task shows 中文, and the steps appear.

### Chinese voice not working

Check **Monitor > Logs > Errors** in Twilio. The error usually names the bad setting. Then try these in `.env`, one at a time, restarting after each:

| Problem | Try |
| --- | --- |
| Menu line in Chinese fails or is silent | `ZH_MENU_SAY_VOICE=Google.cmn-CN-Standard-A` |
| Call drops after pressing 2 | `ZH_TTS_PROVIDER=ElevenLabs`, `ZH_VOICE=` (empty), `ZH_TTS_LANGUAGE=zh-CN` |
| You hear Chinese but it doesn't understand you | `ZH_TRANSCRIPTION_PROVIDER=Deepgram`, `ZH_TRANSCRIPTION_LANGUAGE=zh-CN` |
| Understands you, but speech sounds wrong | `ZH_VOICE=cmn-CN-Wavenet-A` |

### Adding another language

Add phrases to `dialup/i18n.py`, a voice entry to `DEFAULT_VOICES` in `dialup/config.py`, and the code to `LANGUAGES`.
