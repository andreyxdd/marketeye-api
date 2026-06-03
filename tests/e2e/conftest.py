"""HTTP e2e fixtures: patched externals and httpx client."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import api.endpoints.notifications as notifications
import services.analytics_service as analytics_service
import utils.handle_emails as handle_emails
from tests.helpers.stubs import (
    NotifyRecorder,
    stub_get_fcf,
    stub_get_market_sp500,
    stub_get_market_vixs,
    stub_get_ticker_analytics,
    stub_get_ticker_extra_analytics,
)


def _apply_stubs(recorder):
    analytics_service.external_get_ticker_analytics = stub_get_ticker_analytics
    analytics_service.external_get_ticker_extra_analytics = stub_get_ticker_extra_analytics
    analytics_service.get_quarterly_free_cash_flow_polygon = stub_get_fcf
    analytics_service.get_market_sp500 = stub_get_market_sp500
    analytics_service.get_market_vixs = stub_get_market_vixs

    handle_emails.notify_developer = recorder
    notifications.notify_developer = recorder


@pytest.fixture(scope="session", autouse=True)
def _patch_externals_session():
    recorder = NotifyRecorder()
    _apply_stubs(recorder)
    yield recorder


@pytest.fixture
def notify_recorder(_patch_externals_session):
    _patch_externals_session.calls.clear()
    return _patch_externals_session


@pytest.fixture(scope="session", autouse=True)
def _disable_app_mongo_lifecycle():
    from main import app

    app.router.on_startup.clear()
    app.router.on_shutdown.clear()
    yield


@pytest_asyncio.fixture
async def client(mongo_client):
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
