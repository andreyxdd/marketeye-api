"""
 Methods to handle notifications via email
"""
import smtplib
from typing import Optional, Union, List

from core.settings import (
    DEV_SENDER_EMAIL,
    DEV_SENDER_SERVICE_PASSWORD,
    DEV_SENDER_SERVICE,
    DEV_RECIEVER_EMAIL,
    ADDITIONAL_DEV_RECIEVER_EMAIL,
    DEV_SENDER_SERVICE_PORT,
)


def notify_developer(
    recievers: Optional[Union[List[str], str]] = None,
    body: Optional[str] = "Test Notification",
    subject: Optional[str] = "Developer Notification",
):
    """
    Function to notify email (usually when certain code exceptions appears during runtime)

    Args:
        recievers (Optional[Union[list[str], str]], optional):
            emails that recieve message. Defaults to None.
        body (Optional[str], optional):
            message. Defaults to "Test Notification".
    """
    if recievers is None:
        recievers = [DEV_RECIEVER_EMAIL, DEV_SENDER_EMAIL, ADDITIONAL_DEV_RECIEVER_EMAIL]
    elif recievers is str:
        recievers = [recievers, DEV_RECIEVER_EMAIL, ADDITIONAL_DEV_RECIEVER_EMAIL]

    server = smtplib.SMTP_SSL(DEV_SENDER_SERVICE, DEV_SENDER_SERVICE_PORT)
    server.login(DEV_SENDER_EMAIL, DEV_SENDER_SERVICE_PASSWORD)

    for reciever in recievers:
        if reciever:
            msg = (
                f"From: {DEV_SENDER_EMAIL}\r\nTo: {reciever}\r\n"
                + f"Content-Type: text/plain; charset='utf-8'\r\nSubject: {subject}\r\n\r\n"
                + body
            )
            server.sendmail(DEV_SENDER_EMAIL, reciever, msg.encode("utf8"))

    server.quit()
