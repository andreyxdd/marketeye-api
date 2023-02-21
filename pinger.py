"""
Script to ping a web-resource by the PING_URL environmental variable.
It is par for the course approach to keep apps hosted on heroku from sleeping.
The script is called from the heroku scheduler worker. See dashboard fro details.
"""
import os
from datetime import datetime
import requests

from utils.handle_emails import notify_developer

try:
    response = requests.get(os.getenv("PING_URL"))
    print(f"pinger.py responded with: {response}")
    if response.status_code > 200:
        raise Exception("Erroneous status code received")
except Exception as e:  # pylint: disable=W0703
    print(f"pinger.py reported an error: {e}")
    notify_developer(
        body=(
            f"Pinger reported an error at {datetime.utcnow()} UTC time."
            + f" Something went wrong: \n {e}"
        )
    )
