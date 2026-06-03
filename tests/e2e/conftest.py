"""HTTP e2e fixtures: patched externals and httpx client."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import api.endpoints.analytics as analytics_api
import api.endpoints.notifications as notifications
import db.crud.analytics as analytics_crud
import utils.handle_emails as handle_emails
import utils.handle_external_apis as external
from tests.helpers.stubs import (
    NotifyRecorder,
    stub_get_fcf,
    stub_get_market_sp500,
    stub_get_market_vixs,
    stub_get_ticker_analytics,
    stub_get_ticker_extra_analytics,
)


async def stub_cvi_slope(db, date, n_trading_days=50):
    return 0.65


def _apply_stubs(recorder):
    external.get_ticker_analytics = stub_get_ticker_analytics
    external.get_ticker_extra_analytics = stub_get_ticker_extra_analytics
    external.get_quarterly_free_cash_flow_polygon = stub_get_fcf
    external.get_market_sp500 = stub_get_market_sp500
    external.get_market_vixs = stub_get_market_vixs

    analytics_api.get_ticker_analytics = stub_get_ticker_analytics
    analytics_api.get_market_sp500 = stub_get_market_sp500
    analytics_api.get_market_vixs = stub_get_market_vixs
    analytics_api.get_quarterly_free_cash_flow_polygon = stub_get_fcf
    analytics_api.get_normalazied_cvi_slope = stub_cvi_slope

    analytics_crud.get_ticker_extra_analytics = stub_get_ticker_extra_analytics
    analytics_crud.get_quarterly_free_cash_flow_polygon = stub_get_fcf

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
