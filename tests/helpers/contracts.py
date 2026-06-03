"""Contract assertions aligned with marketeye-client types."""

from tests.helpers.constants import DATA_PROPS_KEYS, MARKET_KEYS


def assert_data_props_contract(item: dict) -> None:
    for key in DATA_PROPS_KEYS:
        assert key in item, f"missing key {key}"
    assert isinstance(item["ticker"], str)
    assert isinstance(item["date"], (int, float))
    assert isinstance(item["frequencies"], str)
    assert isinstance(item["fcf"], str)


def assert_market_contract(payload: dict) -> None:
    for key in MARKET_KEYS:
        assert key in payload, f"missing key {key}"
        assert isinstance(payload[key], (int, float))
