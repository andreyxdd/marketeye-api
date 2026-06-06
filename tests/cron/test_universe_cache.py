"""Tests for ticker universe memoization."""

from utils.handle_external_apis import clear_ticker_universe_cache, get_tickers


def test_get_tickers_memoizes_universe_per_market_date(monkeypatch):
    clear_ticker_universe_cache()
    calls = {"count": 0}

    class StubProvider:
        market = "US"

        def fetch_ticker_universe(self, date):
            calls["count"] += 1
            return [f"T-{date}"]

    monkeypatch.setattr(
        "utils.handle_external_apis.get_market_data_provider",
        lambda market="US": StubProvider(),
    )

    first = get_tickers("2024-06-03", market="US")
    second = get_tickers("2024-06-03", market="US")
    other_date = get_tickers("2024-06-04", market="US")

    assert first == ["T-2024-06-03"]
    assert second == first
    assert other_date == ["T-2024-06-04"]
    assert calls["count"] == 2
