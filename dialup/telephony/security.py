"""Optional check that webhooks really come from Twilio (VALIDATE_TWILIO=true)."""
from fastapi import HTTPException, Request
from twilio.request_validator import RequestValidator

from ..services import services


async def twilio_form(request: Request) -> dict[str, str]:
    form = {k: str(v) for k, v in (await request.form()).items()}
    settings = services(request).settings
    if settings.validate_twilio:
        # Twilio signs the public URL it called, not the local one uvicorn sees.
        url = settings.public_url + request.url.path
        if request.url.query:
            url += "?" + request.url.query
        signature = request.headers.get("X-Twilio-Signature", "")
        if not RequestValidator(settings.twilio_token).validate(url, form, signature):
            raise HTTPException(status_code=403, detail="bad Twilio signature")
    return form
