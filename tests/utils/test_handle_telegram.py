"""Unit tests for Telegram developer notifications."""

from unittest.mock import MagicMock

import pytest

import utils.handle_telegram as handle_telegram


def test_notify_developer_posts_to_telegram(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        response = MagicMock()
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(handle_telegram, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(handle_telegram, "TELEGRAM_CHANNEL_ID", "-100123")
    monkeypatch.setattr(handle_telegram.requests, "post", fake_post)

    handle_telegram.notify_developer(body="Something broke", subject="Cronjob Report")

    assert captured["url"] == "https://api.telegram.org/botbot-token/sendMessage"
    assert captured["json"]["chat_id"] == "-100123"
    assert captured["json"]["text"] == "[Market Eye] Cronjob Report\n\nSomething broke"
    assert captured["timeout"] == 30


def test_notify_developer_truncates_long_messages(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        del url, timeout
        captured["text"] = json["text"]
        response = MagicMock()
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(handle_telegram, "TELEGRAM_BOT_TOKEN", "bot-token")
    monkeypatch.setattr(handle_telegram, "TELEGRAM_CHANNEL_ID", "-100123")
    monkeypatch.setattr(handle_telegram.requests, "post", fake_post)

    handle_telegram.notify_developer(body="x" * 5000, subject="Alert")

    assert len(captured["text"]) == 4096
    assert captured["text"].startswith("[Market Eye] Alert")


def test_notify_developer_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(handle_telegram, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(handle_telegram, "TELEGRAM_CHANNEL_ID", None)

    with pytest.raises(RuntimeError, match="Telegram notifications are not configured"):
        handle_telegram.notify_developer(body="test", subject="test")
