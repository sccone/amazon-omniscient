"""Standalone Amazon listing copy generator (title, bullets, description, search terms)."""

import logging
import re

from app.core.exceptions import LLMError
from app.llm.base_client import BaseLLMClient
from app.schemas.listing import ListingRequest, ListingResponse

logger = logging.getLogger(__name__)

TITLE_MAX_CHARS = 200
BULLET_MAX_CHARS = 500
BULLET_COUNT = 5
DESCRIPTION_MAX_CHARS = 2000
SEARCH_TERMS_MAX_BYTES = 249

# Claims Amazon's style guide / prohibited-claims policy rejects or that trigger suppression.
_RISKY_PATTERNS = {
    r"\bbest[- ]?sell(er|ing)\b": "'best seller' claim",
    r"#\s?1\b|\bnumber one\b": "'#1' ranking claim",
    r"\bfree shipping\b": "shipping/promo language",
    r"\b(\d+\s?%\s?off|on sale|discount|limited time)\b": "promotional language",
    r"\b(guarantee[ds]?|money[- ]back)\b": "guarantee wording (verify policy for your category)",
    r"\b(cures?|treats?|prevents?|heals?|fda[- ]approved|clinically proven)\b": "medical/regulatory claim",
    r"\b(eco[- ]friendly|biodegradable|non[- ]toxic)\b": "environmental/safety claim needs substantiation",
}

LISTING_SYSTEM_PROMPT = """You are a senior Amazon listing copywriter who writes conversion-focused, policy-compliant copy for private-label products.

Principles:
1. Specific beats vague. "1.2mm stainless steel, 18 oz" beats "premium quality".
2. Use ONLY facts supplied in the product input. Never invent materials, certifications, dimensions, warranties, or performance numbers. If a detail is missing, leave it out.
3. Answer buyer objections (from the supplied pain points) directly, without disparaging competitors or naming their brands.
4. No hype or prohibited claims: no "best seller", "#1", "free shipping", discounts, medical claims, or unsubstantiated eco/safety claims.
5. Work the highest-priority keywords naturally into the title and first bullets. Never keyword-stuff.
6. Write in the requested language and marketplace conventions (units, spelling).

Always respond with the requested JSON structure only."""


class ListingGenerator:
    """Generates an Amazon listing from free-form product input."""

    def __init__(self, llm_client: BaseLLMClient):
        self.llm = llm_client

    async def generate(self, req: ListingRequest) -> ListingResponse:
        raw = await self.llm.generate_json(
            self._build_prompt(req), max_tokens=4096, system_message=LISTING_SYSTEM_PROMPT
        )
        if not isinstance(raw, dict):
            raise LLMError("Listing generation returned an unexpected shape")
        return self._finalize(raw, req)

    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(req: ListingRequest) -> str:
        def lines(items: list[str]) -> str:
            return "\n".join(f"- {i}" for i in items) if items else "- (none provided)"

        return f"""Write an Amazon listing for the product below.

PRODUCT: {req.product_name}
BRAND: {req.brand or '(none — omit brand from title)'}
CATEGORY: {req.category or '(unspecified)'}
MARKETPLACE: {req.marketplace}   LANGUAGE: {req.language}   TONE: {req.tone}
TARGET AUDIENCE: {req.target_audience or '(unspecified)'}

VERIFIED PRODUCT FACTS (the only claims you may make):
{lines(req.features)}

TARGET KEYWORDS (most important first):
{lines(req.keywords)}

BUYER PAIN POINTS TO ADDRESS:
{lines(req.pain_points)}

COMPETITOR NOTES: {req.competitor_notes or '(none)'}

REQUIREMENTS:
- title: Brand (if given) + primary keyword + key feature + size/variant. Max {TITLE_MAX_CHARS} chars; aim for 120-160. Title Case, no promotional words, no repeated words beyond 2 times.
- bullet_points: exactly {BULLET_COUNT}. Each starts with a 2-4 word ALL CAPS benefit label followed by a colon-free sentence. Aim for 150-250 chars each, max {BULLET_MAX_CHARS}.
- product_description: plain text, max {DESCRIPTION_MAX_CHARS} chars, 2-4 short paragraphs, addresses the pain points. No HTML.
- backend_search_terms: space-separated, max {SEARCH_TERMS_MAX_BYTES} bytes. Synonyms, misspellings, and related terms NOT already in the title or bullets. No brand names, no commas, no repeated words.

Return JSON:
{{
    "title": "...",
    "bullet_points": ["...", "...", "...", "...", "..."],
    "product_description": "...",
    "backend_search_terms": "..."
}}"""

    @staticmethod
    def _finalize(raw: dict, req: ListingRequest) -> ListingResponse:
        warnings: list[str] = []

        title = str(raw.get("title", "")).strip()
        bullets = [str(b).strip() for b in raw.get("bullet_points", []) if str(b).strip()]
        description = str(raw.get("product_description", "")).strip()
        terms = str(raw.get("backend_search_terms", "")).replace(",", " ")

        if not title or not bullets or not description:
            raise LLMError("Listing generation returned incomplete copy")

        if len(title) > TITLE_MAX_CHARS:
            warnings.append(f"Title was {len(title)} chars; truncated to {TITLE_MAX_CHARS}")
            title = title[:TITLE_MAX_CHARS].rsplit(" ", 1)[0]
        if len(bullets) != BULLET_COUNT:
            warnings.append(f"Expected {BULLET_COUNT} bullets, got {len(bullets)}")
        for n, b in enumerate(bullets, 1):
            if len(b) > BULLET_MAX_CHARS:
                warnings.append(f"Bullet {n} is {len(b)} chars (limit {BULLET_MAX_CHARS})")
        if len(description) > DESCRIPTION_MAX_CHARS:
            warnings.append(f"Description was {len(description)} chars; truncated to {DESCRIPTION_MAX_CHARS}")
            description = description[:DESCRIPTION_MAX_CHARS].rsplit(" ", 1)[0]

        # Backend terms: drop words already visible in the listing or equal to the brand, dedupe, cap at 249 bytes.
        visible = set(re.findall(r"[\w'-]+", " ".join([title, *bullets]).lower()))
        if req.brand:
            visible |= set(re.findall(r"[\w'-]+", req.brand.lower()))
        seen: set[str] = set()
        kept: list[str] = []
        size = 0
        for word in terms.split():
            w = word.lower()
            if w in visible or w in seen:
                continue
            cost = len(w.encode()) + (1 if kept else 0)
            if size + cost > SEARCH_TERMS_MAX_BYTES:
                break
            seen.add(w)
            kept.append(w)
            size += cost

        copy_text = " ".join([title, *bullets, description])
        for pattern, label in _RISKY_PATTERNS.items():
            if re.search(pattern, copy_text, re.IGNORECASE):
                warnings.append(f"Possible policy issue: {label}")

        return ListingResponse(
            title=title,
            bullet_points=bullets,
            product_description=description,
            backend_search_terms=" ".join(kept),
            warnings=warnings,
        )
