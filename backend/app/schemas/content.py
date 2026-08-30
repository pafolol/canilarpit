from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator

from app.db.models import EntryType, GuideType, Verdict
from app.services.text import normalize_text, slugify


class FactItem(BaseModel):
    fact: str = Field(min_length=1, max_length=1000)
    citations: list[str] = Field(default_factory=list, max_length=10)


class TalkingPoint(BaseModel):
    opener: str = Field(min_length=1, max_length=500)
    follow_up: str = Field(min_length=1, max_length=1000)
    context: str | None = Field(default=None, max_length=1000)


class VocabularyItem(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    meaning: str = Field(min_length=1, max_length=800)
    example: str | None = Field(default=None, max_length=800)


class QuestionAnswer(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=1500)


class ExtraSection(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class CribSection(BaseModel):
    """One block of the printable crib sheet: a heading and the lines under it."""

    heading: str = Field(min_length=1, max_length=120)
    lines: list[str] = Field(min_length=1, max_length=20)

    @field_validator("lines")
    @classmethod
    def non_empty_lines(cls, lines: list[str]) -> list[str]:
        cleaned = [" ".join(line.split()) for line in lines]
        if any(not line for line in cleaned):
            raise ValueError("crib lines cannot be blank")
        if any(len(line) > 400 for line in cleaned):
            raise ValueError("crib lines cannot exceed 400 characters")
        return cleaned


class LearnPath(BaseModel):
    """The honest alternative to larping: what it costs to actually know the thing."""

    hours: int = Field(ge=0, le=100000)
    book: str = Field(min_length=1, max_length=300)
    make: str = Field(min_length=1, max_length=500)


class LarpProfile(BaseModel):
    """The verdict layer. Every guide answers: can you larp it, and for how long?"""

    entry_type: EntryType
    verdict: Verdict
    exposure_seconds: int | None = Field(default=None, ge=0, le=86400)
    unfalsifiable: bool = False
    flags: list[str] = Field(default_factory=list, max_length=6)
    dek: str = Field(min_length=10, max_length=400)
    crib: list[CribSection] = Field(default_factory=list, max_length=8)
    surface: list[str] = Field(default_factory=list, max_length=10)
    follow_up: list[str] = Field(min_length=1, max_length=10)
    tells: list[str] = Field(min_length=1, max_length=15)
    cost: list[str] = Field(min_length=1, max_length=10)
    learn: LearnPath

    @field_validator("flags")
    @classmethod
    def normalize_flags(cls, flags: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for flag in flags:
            cleaned = " ".join(flag.split()).upper()
            if cleaned and len(cleaned) <= 40 and cleaned not in seen:
                seen.add(cleaned)
                output.append(cleaned)
        return output

    @model_validator(mode="after")
    def validate_clock(self) -> "LarpProfile":
        # Three clock states, and they are mutually exclusive:
        # a countdown, "indefinite" (nothing is checkable), or no clock at all on a DON'T.
        if self.unfalsifiable and self.exposure_seconds is not None:
            raise ValueError("an unfalsifiable guide cannot also carry an exposure clock")
        if self.verdict == Verdict.DONT and self.exposure_seconds is not None:
            raise ValueError("a DON'T verdict has no clock: the answer is not to try")
        if self.verdict != Verdict.DONT and not self.unfalsifiable:
            if self.exposure_seconds is None:
                raise ValueError("exposure_seconds is required unless the guide is unfalsifiable")
            if self.exposure_seconds < 30:
                raise ValueError("exposure_seconds must be at least 30")
        return self


class CommonGuideContent(BaseModel):
    larp: LarpProfile
    overview: str = Field(min_length=1, max_length=5000)
    quick_brief: list[str] = Field(min_length=1, max_length=20)
    essential_facts: list[FactItem] = Field(default_factory=list, max_length=50)
    talking_points: list[TalkingPoint] = Field(default_factory=list, max_length=30)
    vocabulary: list[VocabularyItem] = Field(default_factory=list, max_length=50)
    common_mistakes: list[str] = Field(default_factory=list, max_length=30)
    questions: list[QuestionAnswer] = Field(default_factory=list, max_length=30)
    extra_sections: list[ExtraSection] = Field(default_factory=list, max_length=20)
    spoiler_warning: bool = False


class CharacterItem(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=1200)
    fate: str | None = Field(default=None, max_length=1200)
    relationships: list[str] = Field(default_factory=list, max_length=20)


class MajorEvent(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    spoiler_level: Literal["low", "medium", "major"] = "medium"
    citations: list[str] = Field(default_factory=list, max_length=10)


class AnimeGuideContent(CommonGuideContent):
    kind: Literal["anime"] = "anime"
    premise: str = Field(min_length=1, max_length=3000)
    ending_summary: str | None = Field(default=None, max_length=5000)
    characters: list[CharacterItem] = Field(min_length=1, max_length=100)
    major_events: list[MajorEvent] = Field(default_factory=list, max_length=100)
    fandom_debates: list[str] = Field(default_factory=list, max_length=30)


class BrandItem(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    significance: str = Field(min_length=1, max_length=1000)
    typical_price: str | None = Field(default=None, max_length=120)
    citations: list[str] = Field(default_factory=list, max_length=10)


class MediaScenario(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1200)
    search_terms: list[str] = Field(default_factory=list, max_length=20)
    generation_prompt: str | None = Field(default=None, max_length=2000)


class LifestyleGuideContent(CommonGuideContent):
    kind: Literal["lifestyle"] = "lifestyle"
    aesthetic: str = Field(min_length=1, max_length=3000)
    brands: list[BrandItem] = Field(default_factory=list, max_length=50)
    visual_cues: list[str] = Field(default_factory=list, max_length=50)
    locations: list[str] = Field(default_factory=list, max_length=30)
    media_scenarios: list[MediaScenario] = Field(default_factory=list, max_length=30)


class GeneralGuideContent(CommonGuideContent):
    kind: Literal["general"] = "general"
    key_people: list[str] = Field(default_factory=list, max_length=50)
    timeline: list[str] = Field(default_factory=list, max_length=100)


GuideContent = Annotated[
    AnimeGuideContent | LifestyleGuideContent | GeneralGuideContent,
    Field(discriminator="kind"),
]


class SourceDocument(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    title: str = Field(min_length=1, max_length=300)
    url: AnyHttpUrl
    publisher: str | None = Field(default=None, max_length=160)
    excerpt: str | None = Field(default=None, max_length=2000)
    published_at: datetime | None = None
    verified_at: datetime | None = None

    @field_validator("published_at", "verified_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include a timezone")
        return value.astimezone(UTC)


class GuideDocument(BaseModel):
    schema_version: Literal[1] = 1
    slug: str = Field(min_length=2, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=2, max_length=200)
    summary: str = Field(min_length=10, max_length=1000)
    guide_type: GuideType
    category_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    aliases: list[str] = Field(default_factory=list, max_length=50)
    content: GuideContent
    sources: list[SourceDocument] = Field(default_factory=list, max_length=100)
    last_verified_at: datetime | None = None

    @field_validator("slug", "category_slug", mode="before")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("slug must be a string")
        return slugify(value)

    @field_validator("aliases")
    @classmethod
    def unique_aliases(cls, aliases: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            cleaned = " ".join(alias.split()).strip()
            normalized = normalize_text(cleaned)
            if cleaned and normalized not in seen:
                seen.add(normalized)
                output.append(cleaned)
        return output

    @field_validator("last_verified_at")
    @classmethod
    def require_verification_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("last_verified_at must include a timezone")
        return value.astimezone(UTC)

    @property
    def larp(self) -> LarpProfile:
        return self.content.larp

    @model_validator(mode="after")
    def validate_document_consistency(self) -> "GuideDocument":
        if self.content.kind != self.guide_type.value:
            raise ValueError("content.kind must match guide_type")

        source_keys = [source.key for source in self.sources]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("source keys must be unique")

        citations: set[str] = set()
        for fact in self.content.essential_facts:
            citations.update(fact.citations)
        if isinstance(self.content, AnimeGuideContent):
            for event in self.content.major_events:
                citations.update(event.citations)
        if isinstance(self.content, LifestyleGuideContent):
            for brand in self.content.brands:
                citations.update(brand.citations)

        unknown = citations.difference(source_keys)
        if unknown:
            raise ValueError(f"unknown citation keys: {', '.join(sorted(unknown))}")
        return self
