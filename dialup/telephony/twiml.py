"""TwiML builders."""
from xml.sax.saxutils import escape, quoteattr

from ..config import Settings
from ..i18n import phrases

XML_HEAD = '<?xml version="1.0" encoding="UTF-8"?>'


def relay(settings: Settings, lang: str, greeting: str, params: dict[str, str]) -> str:
    """Hand the call to ConversationRelay in the caller's language.
    Twilio does speech-to-text and text-to-speech."""
    v = settings.voice(lang)
    attrs = {
        "url": f"wss://{settings.public_host}/ws",
        "ttsLanguage": v.tts_language,
        "ttsProvider": v.tts_provider,
        "voice": v.voice,
        "transcriptionLanguage": v.transcription_language,
        "transcriptionProvider": v.transcription_provider,
        "speechModel": v.speech_model,
        # Report the end of a sentence 1s after the caller stops, instead of Twilio's slower auto wait.
        "speechTimeout": "1000",
        "welcomeGreeting": greeting,
        "dtmfDetection": "true",  # keypresses arrive as {"type": "dtmf"} messages (press 1 = yes)
    }
    attr_xml = "".join(f" {k}={quoteattr(val)}" for k, val in attrs.items() if val)
    parameters = "".join(
        f"<Parameter name={quoteattr(k)} value={quoteattr(val)}/>" for k, val in params.items()
    )
    return (
        f"{XML_HEAD}<Response><Connect>"
        f"<ConversationRelay{attr_xml}>{parameters}</ConversationRelay>"
        "</Connect></Response>"
    )


def language_menu(settings: Settings, action: str) -> str:
    """'For English, press 1. 中文服务，请按 2。' Each line in its own voice.
    With no keypress, Twilio still calls `action` and we use the default language."""
    lines = []
    for digit, lang in enumerate(settings.languages, start=1):
        v = settings.voice(lang)
        say_attrs = "".join(
            f" {k}={quoteattr(val)}"
            for k, val in (("language", v.menu_say_language), ("voice", v.menu_say_voice)) if val
        )
        lines.append(f"<Say{say_attrs}>{escape(phrases(lang).menu.format(digit=digit))}</Say>")
    return (
        f"{XML_HEAD}<Response>"
        f'<Gather input="dtmf" numDigits="1" timeout="5" actionOnEmptyResult="true"'
        f" action={quoteattr(action)} method=\"POST\">"
        f"{''.join(lines)}</Gather></Response>"
    )


def sms_reply(text: str) -> str:
    return f"{XML_HEAD}<Response><Message>{escape(text)}</Message></Response>"
