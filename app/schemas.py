"""Shapes of every JSON reply we accept from Claude. A reply that does not match is treated as bad output."""

from pydantic import BaseModel, Field


class JournalLine(BaseModel):
    line: str
    skills: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str
    evidence: str = ""


class Profile(BaseModel):
    summary: str
    break_statement: str = ""
    skills: list[Skill] = Field(default_factory=list)


class JobMatch(BaseModel):
    id: int
    score: int = Field(ge=0, le=100)
    why: str = ""


class JobMatches(BaseModel):
    matches: list[JobMatch]


class JobFit(BaseModel):
    score: int = Field(ge=0, le=100)
    why: str = ""
    talking_points: list[str] = Field(default_factory=list)


class SiteCopy(BaseModel):
    headline: str
    about: str
    services: list[str] = Field(default_factory=list)
