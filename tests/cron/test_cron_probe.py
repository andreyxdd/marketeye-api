"""Tests for slim cron work probe."""

import pytest

from scripts import cron_probe


@pytest.mark.asyncio
async def test_probe_reports_no_work_when_all_markets_are_published(monkeypatch):
    async def no_work(pool, market):
        del pool, market
        return False

    monkeypatch.setattr(cron_probe, "list_markets", lambda: ["US", "TO"])
    monkeypatch.setattr(cron_probe, "needs_ingest", no_work)

    assert not await cron_probe.probe_needs_work(object())


@pytest.mark.asyncio
async def test_probe_reports_work_when_a_market_is_unpublished(monkeypatch):
    async def needs_work(pool, market):
        del pool
        return market == "TO"

    monkeypatch.setattr(cron_probe, "list_markets", lambda: ["US", "TO"])
    monkeypatch.setattr(cron_probe, "needs_ingest", needs_work)

    assert await cron_probe.probe_needs_work(object())


def test_write_needs_work_emits_github_output(tmp_path, monkeypatch):
    output_path = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    cron_probe.write_needs_work(True)

    assert output_path.read_text() == "needs_work=true\n"
