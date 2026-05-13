from pydantic import BaseModel


class WebhookResponse(BaseModel):
    success: bool
