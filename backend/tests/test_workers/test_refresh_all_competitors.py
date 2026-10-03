"""Regression test: the competitor-refresh beat task must select real Niche columns.

The task once selected ``Niche.keyword`` (the column is ``primary_keyword``), which raised
AttributeError on every scheduled run.
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.workers import tasks


@pytest.mark.asyncio
async def test_refresh_all_competitors_selects_primary_keyword_and_queues_each_niche():
    captured = {}

    result = MagicMock()
    result.all.return_value = [(1, "yoga mat"), (2, "water bottle")]

    async def execute(stmt):
        captured["stmt"] = stmt
        return result

    session = MagicMock()
    session.execute = execute
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(tasks, "_get_session_factory", return_value=lambda: session_cm),
        patch.object(tasks.refresh_competitor_data, "delay") as delay,
    ):
        await tasks._refresh_all_competitors_async()

    sql = str(captured["stmt"].compile())
    assert "niches.primary_keyword" in sql
    assert "niches.id" in sql
    assert delay.call_args_list == [call(1, "yoga mat"), call(2, "water bottle")]
