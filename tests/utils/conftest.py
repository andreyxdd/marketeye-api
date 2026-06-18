"""Isolate utils tests from e2e session stubs."""

import pytest

import utils.handle_telegram as handle_telegram

_ORIGINAL_NOTIFY_DEVELOPER = handle_telegram.notify_developer


@pytest.fixture(autouse=True)
def _restore_notify_developer():
    handle_telegram.notify_developer = _ORIGINAL_NOTIFY_DEVELOPER
    yield
