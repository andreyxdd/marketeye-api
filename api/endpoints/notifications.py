"""
Endpoints to make email notifications
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from utils.handle_emails import notify_developer
from utils.handle_validation import validate_api_key

notifications_router = APIRouter()


class Notification(BaseModel):  # pylint: disable=R0903
    """
    Class representing notifications request body
    """

    email_body: str = Field(
        default=None, description="The body of the email to be sent"
    )
    email_subject: str = Field(
        default=None, description="The subject string of the email to be sent"
    )


@notifications_router.get("/", tags=["Notifications"])
async def notifications():
    """
    Initial notifications route endpoint
    """
    return Response("Hello World! It's a Notifications Router")


@notifications_router.post("/notify_developer", tags=["Notifications"])
async def send_developer_notification(
    notification: Notification,
    api_key: str = Depends(validate_api_key),  # pylint: disable=W0613
):
    """
    Endpoint to contact developer.

    Returns: {"detail": "message with status"}
    """
    try:
        notify_developer(
            body=notification.email_body, subject=notification.email_subject
        )
        return {"detail": "Notifications has been sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=e) from e
