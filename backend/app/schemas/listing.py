"""Schemas for the standalone Amazon listing copy generator."""

from pydantic import BaseModel, Field


class ListingRequest(BaseModel):
    """Input describing the product to write a listing for."""

    product_name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    features: list[str] = Field(min_length=1, max_length=20, description="Facts about the product: materials, dimensions, specs, what's in the box")
    keywords: list[str] = Field(default_factory=list, max_length=40, description="Target search keywords, most important first")
    target_audience: str | None = Field(default=None, max_length=300)
    pain_points: list[str] = Field(default_factory=list, max_length=10, description="Buyer complaints in this category the copy should address")
    competitor_notes: str | None = Field(default=None, max_length=1000)
    tone: str = Field(default="clear, specific, trustworthy", max_length=100)
    marketplace: str = Field(default="US", max_length=10)
    language: str = Field(default="English", max_length=30)


class ListingResponse(BaseModel):
    title: str
    bullet_points: list[str]
    product_description: str
    backend_search_terms: str
    warnings: list[str] = Field(default_factory=list, description="Amazon policy/length issues found in the generated copy")
