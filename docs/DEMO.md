# Demo

## Pitch (30 seconds)

3.1 billion people live under mobile internet coverage but don't use it. Nearly all of them can make a phone call.

With Dial-Up, you call a number, say what you need done, and hang up. An AI agent does the task in a real browser. If it needs something only you know, it calls and asks. When it's done, it calls back with the result.

No app, no screen, no data plan. Any phone, in English or Chinese.

## Live demo (3 minutes)

**Before you start:** server running, http://localhost:8000/live full screen on the projector, phone volume up and on speaker. Ideally a teammate who speaks Mandarin does part 2.

### Part 1: English (90 seconds)

1. **Say:** "I'm going to book a bus without touching a screen."
2. Call the Dial-Up number on speaker. Press 1.
3. **Say into the phone:** "Find me the cheapest bus from San Diego to Los Angeles tomorrow and hold a seat."
4. Hang up. **Point at the live view:** "That's the agent working on its own. Searching, comparing prices, picking the cheapest."
5. Phone rings. It asks for a name. Answer.
6. Phone rings again with the seat, price and code.

### Part 2: Chinese (60 seconds)

1. **Say:** "Most people offline don't speak English. Same number, same phone."
2. Call, press 2. The greeting is in Chinese.
3. **Say:** "帮我找明天从圣地亚哥到洛杉矶最便宜的巴士，并帮我订一个座位"
4. Hang up. **Point at the live view:** "The bus site is in English. The agent reads it in English and talks to the caller in Chinese."
5. Answer the name question in Chinese. The result comes back in Chinese.

### Part 3: Knowing when to stop (30 seconds, optional)

Call and ask for a bus to the moon. Let it call back with the reason. If time is short, point at a past stopped task in the live view instead.

## Backup plan

Things that can break live: venue wifi, ngrok, Twilio, phone signal.

- **Record both demos** once they work: screen-record the live view with phone audio on speaker.
- **Hotspot.** If venue wifi is slow, run the laptop off a phone hotspot.
- **Test 10 minutes before demos.** One English call and one Chinese call. If either fails, play its video.
- **Old tasks stay in the live view** after a restart (SQLite), so past successful runs are always there to show.

## Judge Q&A

**Why not just use ChatGPT voice?**
That needs a smartphone and a data plan. Dial-Up works on a basic phone with no internet, by voice or SMS.

**The bus site is fake.**
The agent's tools are general: open, read, click, type. It isn't a scraper for one site. We used a mock site so the demo doesn't depend on a real booking site's uptime.

**How does it know when to stop?**
A guard watches every run. It has hard limits on steps, time and tokens. If the agent repeats itself or clicks with no effect, the guard warns it once, then stops it. Every path ends with a callback.

**What if the caller misses the callback?**
Twilio tells us the call wasn't answered, and Dial-Up calls again.

**How hard is adding a language?**
One file of phrases, one voice config, one setting. The agent already reads sites in one language and talks to the caller in another.

**How does it make money?**
Telcos and NGOs pay per call to reach offline users, the model Viamo already uses for its voice information service. Businesses could also pay to be reachable by these users.

**Who else does this?**
Viamo answers questions over voice on basic phones. Dial-Up does tasks, not just answers.
