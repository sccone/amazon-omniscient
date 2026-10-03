"""Tests for ListingGenerator post-processing and prompt building."""

import pytest
from unittest.mock import AsyncMock

from app.core.exceptions import LLMError
from app.schemas.listing import ListingRequest
from app.services.listing_generator import ListingGenerator


def _req(**kw):
    base = dict(product_name="Steel Water Bottle", brand="Acme", features=["18 oz", "304 stainless steel"], keywords=["water bottle"])
    return ListingRequest(**{**base, **kw})


def _raw(**kw):
    base = {
        "title": "Acme Insulated Water Bottle 18 oz Stainless Steel",
        "bullet_points": [f"BENEFIT {i}: keeps drinks cold for hours" for i in range(5)],
        "product_description": "A bottle made from 304 stainless steel.",
        "backend_search_terms": "flask tumbler bottle acme hydration, tumbler thermos",
    }
    return {**base, **kw}


async def _run(raw, req=None):
    llm = AsyncMock()
    llm.generate_json = AsyncMock(return_value=raw)
    return await ListingGenerator(llm).generate(req or _req())


@pytest.mark.asyncio
async def test_backend_terms_drop_visible_words_brand_and_duplicates():
    out = await _run(_raw())
    words = out.backend_search_terms.split()
    assert "acme" not in words and "bottle" not in words and "stainless" not in words
    assert words.count("tumbler") == 1
    assert "flask" in words and "thermos" in words


@pytest.mark.asyncio
async def test_backend_terms_capped_at_249_bytes():
    out = await _run(_raw(backend_search_terms=" ".join(f"term{i:03d}" for i in range(200))))
    assert len(out.backend_search_terms.encode()) <= 249


@pytest.mark.asyncio
async def test_long_title_truncated_with_warning():
    out = await _run(_raw(title="word " * 80))
    assert len(out.title) <= 200
    assert any("Title" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_flags_policy_risk_and_bullet_count():
    out = await _run(_raw(bullet_points=["BEST SELLER: free shipping on this bottle"]))
    assert any("best seller" in w for w in out.warnings)
    assert any("shipping" in w for w in out.warnings)
    assert any("Expected 5 bullets" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_incomplete_output_raises():
    with pytest.raises(LLMError):
        await _run(_raw(title=""))
    with pytest.raises(LLMError):
        await _run(["not", "a", "dict"])


def test_prompt_contains_inputs():
    p = ListingGenerator._build_prompt(_req(pain_points=["leaks"]))
    assert "304 stainless steel" in p and "leaks" in p and "water bottle" in p
