"""Tool definitions for Claude and the browser actions behind them."""
from playwright.async_api import Page

TOOLS = [
    {
        "name": "goto",
        "description": "Open a URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "read_page",
        "description": "Return the visible text of the current page.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "click",
        "description": "Click the button, link or element with this visible text.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "fill",
        "description": "Type a value into the input with this label.",
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
            "required": ["label", "value"],
        },
    },
    {
        "name": "ask_user",
        "description": "Phone the caller with one short question and wait for the answer. "
                       "Only for information only they have.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "confirm",
        "description": "Phone the caller to approve something irreversible (booking, holding, paying) "
                       "and wait for yes or no. Required before clicking anything like that.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string",
                                       "description": "What you're about to do, one short spoken sentence."}},
            "required": ["summary"],
        },
    },
    {
        "name": "finish",
        "description": "The task is done. The summary is read aloud to the caller.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
    {
        "name": "give_up",
        "description": "The task can't be done. The reason is read aloud to the caller.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]

BROWSER_TOOLS = {"goto", "read_page", "click", "fill"}
PAGE_TEXT_LIMIT = 6000
# Real sites block the default headless user agent more often.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


class Browser:
    """The agent's hands: one page per task."""

    def __init__(self, page: Page):
        self.page = page

    async def run(self, name: str, args: dict) -> str:
        if name == "goto":
            await self.page.goto(args["url"], timeout=20_000, wait_until="domcontentloaded")
            return f"ok, now at {self.page.url}"
        if name == "read_page":
            text = await self.page.inner_text("body")
            return text[:PAGE_TEXT_LIMIT]
        if name == "click":
            t = args["text"]
            target = (
                self.page.get_by_role("button", name=t)
                .or_(self.page.get_by_role("link", name=t))
                .or_(self.page.get_by_text(t))
            )
            await target.first.click(timeout=5_000)
            await self.page.wait_for_load_state()
            return f"ok, now at {self.page.url}"
        if name == "fill":
            label = args["label"]
            target = (  # many real sites use a placeholder or aria name instead of a <label>
                self.page.get_by_label(label)
                .or_(self.page.get_by_placeholder(label))
                .or_(self.page.get_by_role("textbox", name=label))
                .or_(self.page.get_by_role("searchbox", name=label))
                .or_(self.page.get_by_role("combobox", name=label))
            )
            await target.first.fill(args["value"], timeout=5_000)
            return "ok"
        raise ValueError(f"unknown browser tool {name}")
