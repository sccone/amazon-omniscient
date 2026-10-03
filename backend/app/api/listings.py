"""API route for the standalone listing copy generator."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.exceptions import LLMError
from app.dependencies import get_llm_client
from app.llm.base_client import BaseLLMClient
from app.schemas.listing import ListingRequest, ListingResponse
from app.services.listing_generator import ListingGenerator

router = APIRouter(prefix="/listings", tags=["listings"])


@router.post("/generate", response_model=ListingResponse)
async def generate_listing(
    body: ListingRequest,
    llm: BaseLLMClient = Depends(get_llm_client),
) -> ListingResponse:
    """Generate an Amazon title, 5 bullets, description and backend search terms
    from product facts and target keywords. No database or scraping involved."""
    try:
        return await ListingGenerator(llm).generate(body)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
