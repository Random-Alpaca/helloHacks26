from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Course:
    key: str          # join key, e.g. "UBCV,2026W1,CPSC,CPSC121,101"
    code: str         # e.g. "CPSC 121"
    section: str      # e.g. "101"
    term: str         # e.g. "2026W1"
    title: str        # e.g. "Models of Computation"
    grade: float | None = None
    schedule: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class Item:
    id: str           # "source:type:upstream_id", e.g. "canvas:assignment:123456"
    course_key: str
    kind: str         # one of: assignment | quiz | exam | event | announcement
    title: str
    source: str
    due: datetime | None = None
    url: str | None = None
    done: bool = False


@dataclass
class Textbook:
    course_key: str
    title: str
    isbn: str
    required: bool
    price_new: float | None = None
    price_digital: float | None = None
    store_url: str | None = None
