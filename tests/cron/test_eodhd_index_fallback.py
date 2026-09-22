"""EODHD index EOD fallback when Markets Insider fails for SP500/VIX."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import RequestException

from utils import handle_external_apis as external


@pytest.fixture
def bypass_redis_cache(monkeypatch):
    client = MagicMock()
    client.get.return_value = None
    monkeypatch.setattr(external.cache, "client", client)


def _eodhd_bars(closes):
    return [{"date": f"2024-01-{i+1:02d}", "close": c} for i, c in enumerate(closes)]


def test_fetch_eodhd_index_closes_helper_returns_chronological_closes(monkeypatch):
    response = MagicMock(status_code=200)
    response.json.return_value = _eodhd_bars([10.0, 11.0, 12.5])

    def fake_get(url, params=None, timeout=None):
        assert url == "https://eodhd.com/api/eod/GSPC.INDX"
        assert params["from"] == "2024-01-01"
        assert params["to"] == "2024-01-03"
        assert params["period"] == "d"
        assert params["fmt"] == "json"
        assert "api_token" in params
        return response

    monkeypatch.setattr(external.requests, "get", fake_get)

    closes = external._fetch_eodhd_index_closes("GSPC.INDX", "2024-01-01", "2024-01-03")
    assert closes == [10.0, 11.0, 12.5]


def test_fetch_eodhd_index_closes_helper_raises_on_non_200(monkeypatch):
    secret = "test-eodhd-secret-do-not-leak"
    monkeypatch.setattr(external, "EODHD_API_KEY", secret)
    response = MagicMock(status_code=500, text="boom")
    monkeypatch.setattr(external.requests, "get", lambda *a, **k: response)

    with pytest.raises(Exception, match="500") as exc_info:
        external._fetch_eodhd_index_closes("VIX.INDX", "2024-01-01", "2024-01-03")
    err = str(exc_info.value)
    assert "api_token=" not in err
    assert secret not in err
    assert "VIX.INDX" in err
    assert "from=2024-01-01" in err
    assert "to=2024-01-03" in err


def test_fetch_eodhd_index_closes_helper_raises_on_empty_bars(monkeypatch):
    secret = "test-eodhd-secret-do-not-leak"
    monkeypatch.setattr(external, "EODHD_API_KEY", secret)
    response = MagicMock(status_code=200)
    response.json.return_value = []
    monkeypatch.setattr(external.requests, "get", lambda *a, **k: response)

    with pytest.raises(Exception, match="empty") as exc_info:
        external._fetch_eodhd_index_closes("VIX.INDX", "2024-01-01", "2024-01-03")
    err = str(exc_info.value)
    assert "api_token=" not in err
    assert secret not in err


def test_fetch_eodhd_index_closes_helper_error_omits_api_token(monkeypatch):
    secret = "leaky-token-value-xyz"
    monkeypatch.setattr(external, "EODHD_API_KEY", secret)

    def boom(*args, **kwargs):
        del args, kwargs
        raise RequestException(
            f"HTTPSConnectionPool: https://eodhd.com/api/eod/GSPC.INDX"
            f"?api_token={secret}&from=2024-01-01"
        )

    monkeypatch.setattr(external.requests, "get", boom)

    with pytest.raises(Exception) as exc_info:
        external._fetch_eodhd_index_closes("GSPC.INDX", "2024-01-01", "2024-01-03")
    err = str(exc_info.value)
    assert "api_token=" not in err
    assert secret not in err
    assert exc_info.value.__cause__ is None


def test_get_market_sp500_falls_back_to_eodhd_when_mi_fails(
    monkeypatch, bypass_redis_cache
):
    del bypass_redis_cache

    def mi_fail(url, label):
        raise Exception(f"MI 500 ({label})")

    monkeypatch.setattr(external, "_market_insider_request", mi_fail)
    monkeypatch.setattr(
        external,
        "_fetch_eodhd_index_closes",
        lambda symbol, from_date, to_date: [100.0, 200.0, 4500.5],
    )

    assert external.get_market_sp500("2024-06-03") == 4500.5


def test_get_market_sp500_unchanged_when_mi_ok(monkeypatch, bypass_redis_cache):
    del bypass_redis_cache
    response = MagicMock()
    response.json.return_value = [{"Close": 5100.25}]

    monkeypatch.setattr(
        external, "_market_insider_request", lambda url, label: response
    )
    monkeypatch.setattr(
        external,
        "_fetch_eodhd_index_closes",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("EODHD must not run")),
    )

    assert external.get_market_sp500("2024-06-03") == 5100.25


def test_get_market_sp500_raises_when_both_fail(monkeypatch, bypass_redis_cache):
    del bypass_redis_cache

    monkeypatch.setattr(
        external,
        "_market_insider_request",
        lambda url, label: (_ for _ in ()).throw(Exception("MI down")),
    )
    monkeypatch.setattr(
        external,
        "_fetch_eodhd_index_closes",
        lambda *a, **k: (_ for _ in ()).throw(Exception("EODHD down")),
    )

    with pytest.raises(Exception, match="get_market_sp500") as exc_info:
        external.get_market_sp500("2024-06-03")
    assert exc_info.value.__cause__ is not None
    assert "EODHD" in str(exc_info.value.__cause__)


def test_get_market_vixs_falls_back_to_eodhd_when_mi_fails(
    monkeypatch, bypass_redis_cache
):
    del bypass_redis_cache
    closes = [float(i) for i in range(1, 56)]  # 55 bars, chronological

    monkeypatch.setattr(
        external,
        "_market_insider_request",
        lambda url, label: (_ for _ in ()).throw(Exception("MI 500")),
    )
    monkeypatch.setattr(
        external,
        "_fetch_eodhd_index_closes",
        lambda symbol, from_date, to_date: closes,
    )

    result = external.get_market_vixs("2024-06-03")
    assert result["VIX"] == 55.0
    assert result["VIX1"] == 54.0
    assert result["VIX2"] == 53.0
    assert "VIX_50days_EMA" in result
    assert isinstance(result["VIX_50days_EMA"], float)


def test_get_market_vixs_unchanged_when_mi_ok(monkeypatch, bypass_redis_cache):
    del bypass_redis_cache
    response = MagicMock()
    # newest first, matching Markets Insider order
    response.json.return_value = [
        {"Close": 18.0},
        {"Close": 17.0},
        {"Close": 16.0},
    ] + [{"Close": 15.0}] * 50

    monkeypatch.setattr(
        external, "_market_insider_request", lambda url, label: response
    )
    monkeypatch.setattr(
        external,
        "_fetch_eodhd_index_closes",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("EODHD must not run")),
    )

    result = external.get_market_vixs("2024-06-03")
    assert result["VIX"] == 18.0
    assert result["VIX1"] == 17.0
    assert result["VIX2"] == 16.0


def test_get_market_vixs_raises_when_both_fail(monkeypatch, bypass_redis_cache):
    del bypass_redis_cache

    monkeypatch.setattr(
        external,
        "_market_insider_request",
        lambda url, label: (_ for _ in ()).throw(Exception("MI down")),
    )
    monkeypatch.setattr(
        external,
        "_fetch_eodhd_index_closes",
        lambda *a, **k: (_ for _ in ()).throw(Exception("EODHD down")),
    )

    with pytest.raises(Exception, match="get_market_vixs") as exc_info:
        external.get_market_vixs("2024-06-03")
    assert exc_info.value.__cause__ is not None
