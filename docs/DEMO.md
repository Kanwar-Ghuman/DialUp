# Demo

## Pitch (30 seconds)

3.1 billion people live within mobile internet coverage but don't use it (GSMA). Most don't own a smartphone, and many don't own a phone at all. A voice call works from any phone: basic, shared or borrowed.

With Dial-Up, you call a number, say what you need done, and hang up. An AI agent does the task in a real browser. If it needs something only you know, it calls and asks. When it's done, it calls back with the result.

No app, no screen, no data plan. English or Chinese.

## Format

Judging happens in two rounds:

1. **Video (everyone).** Judges watch a recorded video and pick the top 5 teams.
2. **Live pitch (top 5).** Run the live demo below.

The video is what gets you to the second round, so record it first and make it great.

## Video

Use one take per part and cut them together. Screen-record the live view, with the phone on speaker so the mic picks up both sides of every call. `CALL_DELAY` in `.env` waits 8 seconds before each callback. Use that gap to narrate over the live view, then cut it down in editing if it drags.

1. **Hook (10 seconds):** the first line of the pitch over a shot of a basic phone.
2. **English clinic booking:** part 1 below, end to end. Show the follow-up questions on the first call, the confirm callback (press 1), and the result with the confirmation number.
3. **Real website (20 seconds):** call and ask something factual, like "What time does the Apple Store at UTC in San Diego close today?" Show the agent searching and reading the real site in the live view.
4. **Chinese (30 seconds):** part 2 below. Speed up the waiting parts.
5. **Close (10 seconds):** "The internet, one call away. Dial it in."

Record each part twice, and keep the best take.

## Live demo (3 minutes)

**Before you start:** server running, http://localhost:8000/live full screen on the projector, phone volume up and on speaker. Ideally a teammate who speaks Mandarin does part 2.

### Part 1: English (90 seconds)

1. **Say:** "I'm going to book a doctor's appointment without touching a screen."
2. Call the Dial-Up number on speaker. Press 1.
3. **Say into the phone:** "Book me a flu shot at the community clinic this week, in the morning."
   It asks for anything missing (the patient's name and date of birth). Answer, let it read the task back, and it hangs up.
4. **Point at the live view:** "That's the agent working on its own. Filling in the form, skipping the full slots, picking a morning."
5. Phone rings: "Book a flu shot on Tuesday at 9 AM with Dr. Chen? Say yes or press 1." **Press 1.**
   **Say:** "It can't book anything until I say yes. That's enforced in code, not just in the prompt."
6. Phone rings again with the day, time and confirmation number.

Backup flow: the bus booking ("Find me the cheapest bus from San Diego to Los Angeles tomorrow and hold a seat") works the same way.

### Part 2: Chinese (60 seconds)

1. **Say:** "Most people offline don't speak English. Same number, same phone."
2. Call, press 2. The greeting is in Chinese.
3. **Say:** "帮我在社区诊所约一个这周上午的流感疫苗。" Answer any follow-up (name: "我叫…"). Let it finish talking before you answer.
4. **Point at the live view:** "The clinic site is in English. The agent reads it in English and talks to the caller in Chinese."
5. Confirm call: say "是的" (or press 1). Avoid 没问题 / anything with 不. The result comes back in Chinese.

### Part 3: Knowing when to stop (30 seconds, optional)

Three endings, all with a callback: **done** (parts 1 and 2), **gave up** (ask for a bus to the moon), and **stopped**.
For "stopped", run a task with a tiny budget beforehand (`python scripts/try_agent.py --budget 0.03 "..."`) and point at it in the live view:
the guard stopped it before it went over budget, and the caller still heard what it found.

## Backup plan

Things that can break live: venue wifi, ngrok, Twilio, phone signal.

- **The video doubles as the backup.** If a live call fails, play that part of the video.
- **Hotspot.** If venue wifi is slow, run the laptop off a phone hotspot.
- **Test 10 minutes before demos.** One English call and one Chinese call. If either fails, play its video.
- **Old tasks stay in the live view** after a restart (SQLite), so past successful runs are always there to show.

## Judge Q&A

**Why not just call 1-800-ChatGPT?**
It answers questions over the phone, in the US and Canada. Dial-Up does tasks: it works a real website for you, calls back when it needs you, and calls back with the result. Voice or SMS, any phone.

**The clinic site is fake.**
The agent's tools are general: open, read, click, type. It isn't a scraper for one site. We used demo sites for bookings so the demo doesn't depend on a real site's uptime, and because real booking sites need logins or payment, which the agent refuses on purpose. For facts it uses the real web: ask it when a store closes today and watch it read the real page.

**How does this reach a billion people?**
Today it's one server and one number. At scale: local or toll-free numbers per country through carrier partners, so calling is free (it already calls you back, which fits the "missed call" habit in many markets); stateless workers behind a queue with a browser pool; partner integrations for high-value services like clinics and benefits; paid for by telcos, NGOs and governments that want to reach people offline. About 5 cents of AI per task today. See "Scaling to a billion people" in the README.

**How does it know when to stop?**
A guard watches every run with measurable signals, not the agent's own opinion. It stops *before* a task would go over its dollar budget, and it has hard limits on steps and time. If the agent repeats itself or clicks with no effect, the guard warns it once, then stops it. Every path ends with a callback that says what it found.

**What stops it from booking or paying by mistake?**
Rules in code, not the prompt: clicks like Hold, Book or Pay are blocked until the caller says yes (or presses 1) on a confirm call, and it never types passwords, card numbers or ID numbers. Web page text is treated as data, never as instructions.

**What if the caller misses the callback?**
Twilio tells us the call wasn't answered, and Dial-Up calls again.

**How hard is adding a language?**
One file of phrases, one voice config, one setting. The agent already reads sites in one language and talks to the caller in another.

**How does it make money?**
Telcos and NGOs pay per call to reach offline users, the model Viamo already uses for its voice information service. Businesses could also pay to be reachable by these users.

**Who else does this?**
Viamo answers questions over voice on basic phones. Dial-Up does tasks, not just answers.
