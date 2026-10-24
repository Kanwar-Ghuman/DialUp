"""Supervisor for an unattended agent run: decides when to nudge it and when to stop it.

Hard limits stop the run right away: steps, wall-clock time, tokens.
Spinning (repeating an action, or clicking with no effect) gets one warning,
then a stop if it happens again.
"""
import hashlib
import json
import time
from collections import Counter, deque
from dataclasses import dataclass


@dataclass
class Verdict:
    action: str      # "ok", "warn" or "stop"
    reason: str = ""  # reads after "I ..." / "you ...", e.g. "repeated the same action 3 times"


class Guard:
    LOOP_WINDOW = 8     # look at the last N actions
    LOOP_REPEATS = 3    # same action this many times in the window = loop
    NO_EFFECT = 3       # clicks/gotos in a row that didn't change the page = stuck

    def __init__(self, max_steps: int, max_seconds: float, token_budget: int):
        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self.token_budget = token_budget
        self.steps = 0
        self.tokens = 0
        self.started = time.monotonic()
        self._actions: deque[str] = deque(maxlen=self.LOOP_WINDOW)
        self._last_page: str | None = None
        self._last_was_nav = False
        self._no_effect = 0
        self._warned = False

    # ---- record what happened ----

    def record_tokens(self, n: int) -> None:
        self.tokens += n

    def record_action(self, name: str, args: dict) -> None:
        self.steps += 1
        self._last_was_nav = name in {"click", "goto"}
        if name != "read_page":  # reading after every action is expected, not a loop
            self._actions.append(name + json.dumps(args, sort_keys=True))

    def record_page(self, text: str) -> None:
        h = hashlib.sha1(text.encode()).hexdigest()
        if self._last_was_nav and h == self._last_page:
            self._no_effect += 1
        elif h != self._last_page:
            self._no_effect = 0
        self._last_page = h

    # ---- decide ----

    def check(self) -> Verdict:
        if self.steps >= self.max_steps:
            return Verdict("stop", f"hit the {self.max_steps} step limit")
        if time.monotonic() - self.started > self.max_seconds:
            return Verdict("stop", f"ran past {int(self.max_seconds // 60)} minutes")
        if self.tokens > self.token_budget:
            return Verdict("stop", "used up my budget for this task")

        problem = self._spinning()
        if not problem:
            return Verdict("ok")
        if self._warned:
            return Verdict("stop", problem)
        self._warned = True
        self._actions.clear()  # give it a clean chance after the warning
        self._no_effect = 0
        return Verdict("warn", problem)

    def _spinning(self) -> str | None:
        if self._actions:
            _, n = Counter(self._actions).most_common(1)[0]
            if n >= self.LOOP_REPEATS:
                return f"repeated the same action {n} times"
        if self._no_effect >= self.NO_EFFECT:
            return "kept clicking without the page changing"
        return None
