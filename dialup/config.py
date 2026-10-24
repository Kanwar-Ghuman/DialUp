"""Settings, loaded once from environment variables (.env)."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Voice:
    """ConversationRelay speech settings for one language. Empty string = Twilio's default."""
    tts_language: str
    tts_provider: str
    voice: str
    transcription_language: str
    transcription_provider: str
    speech_model: str
    menu_say_language: str  # <Say> language for the menu line
    menu_say_voice: str     # <Say> voice for the menu line


# Defaults. Every field can be overridden in .env, e.g. ZH_TTS_PROVIDER=ElevenLabs
DEFAULT_VOICES = {
    "en": Voice(
        tts_language="en-US", tts_provider="ElevenLabs", voice="",
        transcription_language="en-US", transcription_provider="Deepgram", speech_model="",
        menu_say_language="en-US", menu_say_voice="Polly.Joanna-Neural",
    ),
    "zh": Voice(
        tts_language="cmn-CN", tts_provider="Google", voice="cmn-CN-Standard-A",
        transcription_language="cmn-Hans-CN", transcription_provider="Google", speech_model="",
        menu_say_language="cmn-CN", menu_say_voice="Polly.Zhiyu",
    ),
}


def _voice(lang: str) -> Voice:
    base = DEFAULT_VOICES[lang]
    p = lang.upper() + "_"
    return Voice(**{f: os.getenv(p + f.upper(), getattr(base, f)) for f in base.__dataclass_fields__})


@dataclass(frozen=True)
class Settings:
    twilio_sid: str
    twilio_token: str
    twilio_number: str
    public_host: str        # ngrok host, no scheme
    site_base: str          # where the agent finds the mock sites
    model: str
    max_steps: int          # guard: browser steps per task
    max_minutes: float      # guard: wall-clock time per task
    token_budget: int       # guard: total model tokens per task
    ask_timeout: int        # seconds to wait for the caller to answer a question
    result_hold: int        # seconds to keep the result call open
    max_concurrent: int     # tasks running at once
    callback_retries: int   # extra tries if the result call isn't answered
    validate_twilio: bool   # check X-Twilio-Signature on webhooks
    db_path: str
    languages: tuple[str, ...] = ("en", "zh")   # menu order: first is 1, second is 2
    default_language: str = "en"
    voices: dict[str, Voice] = field(default_factory=lambda: dict(DEFAULT_VOICES))
    cost_budget: float = 0.50   # guard: USD per task, stops before crossing it (0 = off)
    price_in: float = 2.0       # USD per million input tokens (Sonnet 5.5)
    price_out: float = 10.0     # USD per million output tokens (Sonnet 5.5)
    speech_pause: float = 2.0   # seconds of silence before the caller counts as done talking
    call_delay: float = 0.0     # seconds to wait before each outbound call (pacing for demos)

    @property
    def public_url(self) -> str:
        return f"https://{self.public_host}"

    def voice(self, lang: str) -> Voice:
        return self.voices.get(lang) or self.voices[self.default_language]


def load_settings() -> Settings:
    host = os.environ["PUBLIC_HOST"].removeprefix("https://").removeprefix("http://").rstrip("/")
    languages = tuple(
        code for code in (c.strip() for c in os.getenv("LANGUAGES", "en,zh").split(","))
        if code in DEFAULT_VOICES
    ) or ("en",)
    default = os.getenv("DEFAULT_LANGUAGE", languages[0])
    return Settings(
        twilio_sid=os.environ["TWILIO_SID"],
        twilio_token=os.environ["TWILIO_TOKEN"],
        twilio_number=os.environ["TWILIO_NUMBER"],
        public_host=host,
        site_base=os.getenv("SITE_BASE", f"https://{host}").rstrip("/"),
        model=os.getenv("MODEL", "claude-sonnet-5-5"),
        max_steps=int(os.getenv("MAX_STEPS", "25")),
        max_minutes=float(os.getenv("MAX_MINUTES", "15")),
        token_budget=int(os.getenv("TOKEN_BUDGET", "400000")),
        ask_timeout=int(os.getenv("ASK_TIMEOUT", "180")),
        result_hold=int(os.getenv("RESULT_HOLD", "15")),
        max_concurrent=int(os.getenv("MAX_CONCURRENT", "3")),
        callback_retries=int(os.getenv("CALLBACK_RETRIES", "1")),
        validate_twilio=_bool("VALIDATE_TWILIO", False),
        db_path=os.getenv("DB_PATH", "dialup.db"),
        languages=languages,
        default_language=default if default in languages else languages[0],
        voices={lang: _voice(lang) for lang in DEFAULT_VOICES},
        cost_budget=float(os.getenv("COST_BUDGET", "0.50")),
        price_in=float(os.getenv("PRICE_IN", "2.0")),
        price_out=float(os.getenv("PRICE_OUT", "10.0")),
        speech_pause=float(os.getenv("SPEECH_PAUSE", "2.0")),
        call_delay=float(os.getenv("CALL_DELAY", "0")),
    )
