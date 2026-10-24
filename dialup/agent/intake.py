"""Live intake: before hanging up, make sure the task has the details the agent will need."""
from ..i18n import phrases

MAX_FOLLOW_UPS = 3

INTAKE_TOOL = {
    "name": "intake_decision",
    "description": "Decide whether the caller's request has enough detail to start working.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ready": {"type": "boolean", "description": "True if the task can start now."},
            "question": {"type": "string", "description": "If not ready: one short follow-up question."},
            "task": {"type": "string", "description": "The full task with every detail the caller gave."},
        },
        "required": ["ready", "task"],
    },
}


def _system(language: str) -> str:
    p = phrases(language)
    return f"""You are on a phone call taking a request for a web task. Someone else does the task later,
and they can only reach the caller by calling back, so get the important details now.

Ask a follow-up only for details the task clearly needs and the caller hasn't given, for example:
- bookings: from where, to where, which day, how many people, the name to book under
- doctor appointments: what the visit is for, which days or times work, the patient's full name and date of birth
- shopping: which item, size or quantity, budget
Speech-to-text makes mistakes. If a place name or number sounds garbled, ask them to repeat it.
Don't ask about things that don't matter. If the caller wants you to just pick, that's fine.
Never ask the same question twice. If their latest reply answers it, even roughly, move on.

Always answer by calling intake_decision.
The question is read aloud: write it in {p.name}, one short plain sentence, no symbols.
Write task in {p.name} as one or two plain sentences with every detail, under 30 words."""


async def clarify(llm, model: str, language: str, turns: list[str]) -> tuple[str | None, str]:
    """Returns (follow-up question or None, task). Out of follow-ups or on error: start anyway."""
    transcript = "\n".join(f"Caller: {t}" for t in turns)
    follow_ups_left = MAX_FOLLOW_UPS - (len(turns) - 1)
    if follow_ups_left <= 0:
        transcript += "\n\nNo more questions allowed. Set ready to true."
    try:
        reply = await llm.messages.create(
            model=model, max_tokens=400, system=_system(language),
            tools=[INTAKE_TOOL], messages=[{"role": "user", "content": transcript}],
        )
        decision = next(b.input for b in reply.content if b.type == "tool_use")
    except Exception as e:  # never keep the caller hanging; the agent can still ask later
        print(f"[call]   intake check failed, starting anyway: {type(e).__name__}: {e}", flush=True)
        return None, " ".join(turns)
    task = (decision.get("task") or "").strip() or " ".join(turns)
    question = (decision.get("question") or "").strip()
    if decision.get("ready") or not question or follow_ups_left <= 0:
        return None, task
    return question, task
