"""
Endpoints to make email notifications
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.settings import API_KEY
from utils.handle_emails import notify_developer

notifications_router = APIRouter()


class Notification(BaseModel):  # pylint: disable=R0903
    """
    Class representing notifications request body
    """

    email_body: str
    email_subject: str


@notifications_router.get("/")
async def home():
    """
    Initial notifications route

    Returns:

        Response: welcome sign
    """
    return Response("Hello World! It's a Notifications Router")


@notifications_router.post("/notify_developer")
async def run_developer_notification(notification: Notification, api_key: str):
    """[summary]

    Args:
        notification (Notification): Notifications body object
        api_key (str): key to allow/disallow a request

    Raises:
        HTTPException: Incorrect API key provided
        HTTPException: Notifications has not been sent due to internal error

    Returns:
        dict: {"detail": "message with status"}
    """
    if api_key != API_KEY:
        raise HTTPException(status_code=400, detail="Erreneous API key recieved.")

    try:
        notify_developer(
            body=notification.email_body, subject=notification.email_subject
        )
        return {"detail": "Notifications has been sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=e) from e
