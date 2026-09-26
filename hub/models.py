"""Shared model every adapter returns. Keep it tiny (see issue #1)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Course:
    code: str
    section: str
    term: str
    title: str
    grade: float | None = None  # current score %, Canvas only


@dataclass
class Item:
    course: str
    kind: Literal["assignment", "event", "announcement"]
    title: str
    due: datetime | None
    url: str
    source: str


@dataclass
class Textbook:
    course: str
    title: str
    isbn: str
    required: bool
    price: float | None
    url: str
