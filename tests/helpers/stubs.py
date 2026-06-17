"""Shared stubs for external APIs in HTTP e2e tests."""

from tests.helpers.fixture_loader import load_json


def stub_get_ticker_analytics(ticker, date, *args, **kwargs):
    data = load_json("external/ticker_analytics.json")
    payload = data[ticker.upper()]
    return payload


def stub_get_ticker_extra_analytics(ticker, date, *args, **kwargs):
    data = load_json("external/ticker_extra.json")
    return data[ticker.upper()]


def stub_get_fcf(ticker, date_quarter, *args, **kwargs):
    data = load_json("external/fcf.json")
    return data[ticker.upper()]


def stub_get_market_sp500(date, *args, **kwargs):
    return load_json("external/sp500.json")["SP500"]


def stub_get_market_vixs(date, *args, **kwargs):
    return load_json("external/vix.json")


class NotifyRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})


def apply_external_stubs(monkeypatch):
    import utils.handle_telegram as handle_telegram
    import utils.handle_external_apis as external

    monkeypatch.setattr(external, "get_ticker_analytics", stub_get_ticker_analytics)
    monkeypatch.setattr(
        external, "get_ticker_extra_analytics", stub_get_ticker_extra_analytics
    )
    monkeypatch.setattr(
        external,
        "get_quarterly_free_cash_flow_polygon",
        stub_get_fcf,
    )
    monkeypatch.setattr(external, "get_market_sp500", stub_get_market_sp500)
    monkeypatch.setattr(external, "get_market_vixs", stub_get_market_vixs)

    recorder = NotifyRecorder()
    monkeypatch.setattr(handle_telegram, "notify_developer", recorder)
    return recorder
