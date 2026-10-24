"""Everything the caller hears or reads, per language. Add a language here and in config.py."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Phrases:
    name: str            # how the agent prompt names the language
    price_example: str   # how the agent should say a price out loud
    menu: str            # language menu line, {digit} filled in
    greeting: str
    got_it_task: str     # {task} filled in; read back at the end of the intake call
    got_it_sms: str
    thanks: str
    late_answer: str
    goodbye: str
    sms_reply_hint: str
    sms_empty: str
    gave_up: str         # {reason} filled in
    stopped: str         # {reason} filled in (may be ignored)
    crash: str
    no_answer: str       # two question calls went unanswered
    confirm: str         # {summary} filled in; read to the caller before anything irreversible


PHRASES: dict[str, Phrases] = {
    "en": Phrases(
        name="English",
        price_example="19 dollars",
        menu="For English, press {digit}.",
        greeting="Hi, this is Dial-Up. Tell me what you need done online.",
        got_it_task="Got it. {task} I'm working on it and will call you back.",
        got_it_sms="Got it. I'm working on it and will text you back.",
        thanks="Thanks. Back to work.",
        late_answer="Thanks. That question already timed out, but I'll still call you with the result.",
        goodbye="Okay. Call this number anytime for something new.",
        sms_reply_hint="(Reply to this text.)",
        sms_empty="Text me what you need done online.",
        gave_up="Sorry, I couldn't do that. {reason}",
        stopped="Sorry, I had to stop. I {reason}. Try asking a simpler way.",
        crash="Sorry, something went wrong on our side. Please call again.",
        no_answer="I needed a quick answer from you but couldn't reach you, so I stopped. Call again anytime.",
        confirm="{summary} Say yes to go ahead, or no to cancel.",
    ),
    "zh": Phrases(
        name="Simplified Mandarin Chinese",
        price_example="19美元",
        menu="中文服务，请按 {digit}。",
        greeting="你好，这里是 Dial-Up。请告诉我你需要在网上办什么事。",
        got_it_task="收到。{task} 我现在就去办，办好后给你回电话。",
        got_it_sms="收到。我现在就去办，办好后给你发短信。",
        thanks="谢谢，我继续去办。",
        late_answer="谢谢。这个问题已经超时了，不过我还是会打电话告诉你结果。",
        goodbye="好的。有需要随时打这个号码。",
        sms_reply_hint="（请直接回复这条短信。）",
        sms_empty="请发短信告诉我你需要在网上办什么事。",
        gave_up="抱歉，这件事我办不了。{reason}",
        stopped="抱歉，我不得不停下来。请换一种更简单的说法再试一次。",
        crash="抱歉，我们这边出了点问题。请再打一次。",
        no_answer="我需要问你一个问题，但没能联系上你，所以先停下了。有需要随时再打来。",
        confirm="{summary} 确认请说“是”，取消请说“不”。",
    ),
}

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def phrases(lang: str) -> Phrases:
    return PHRASES.get(lang, PHRASES["en"])


def detect(text: str, enabled: tuple[str, ...], default: str) -> str:
    """For SMS: Chinese characters mean Chinese, otherwise the default."""
    if "zh" in enabled and _CJK.search(text):
        return "zh"
    return default
