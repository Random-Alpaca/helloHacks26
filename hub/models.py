"""Shared model every adapter returns. Keep it tiny (see issue #1)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Category = Literal["task", "deadline", "material"]

# What bucket a given kind falls into. Adapters pick a specific `kind`
# ("assignment", "quiz", "reading", ...); this decides which of the three
# lists (tasks / deadlines-and-key-dates / materials) it shows up in.
# Unlisted kinds default to "task" - the safest bucket for "something to deal with".
CATEGORY_FOR: dict[str, Category] = {
    "assignment": "task",
    "announcement": "task",
    "quiz": "deadline",
    "exam": "deadline",
    "event": "deadline",  # calendar events: breaks, key dates, office hours
    "break": "deadline",
    "payment": "deadline",  # e.g. tuition due
    "reading": "material",
    "textbook": "material",
}


def category_for(kind: str) -> Category:
    return CATEGORY_FOR.get(kind, "task")


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
    category: Category
    kind: str  # specific label within the category, e.g. "quiz", "reading" - free-form, new providers can add one without touching this file
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
