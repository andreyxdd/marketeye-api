import pytest

from tests.helpers.constants import FIXTURE_API_KEY


@pytest.mark.asyncio
async def test_notify_developer_success(client, notify_recorder):
    notify_recorder.calls.clear()
    response = await client.post(
        "/api/notifications/notify_developer",
        params={"api_key": FIXTURE_API_KEY},
        json={"email_body": "test body", "email_subject": "test subject"},
    )
    assert response.status_code == 200
    assert "detail" in response.json()
    assert len(notify_recorder.calls) == 1
