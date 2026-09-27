"""Pure functions on the shared model: sort/rank items, course-code parsing,
identity ops. Nothing here touches SQL or a provider - see hub/db.py and
hub/<provider>.py for those.

sort_items() is design.md's "Ranking" section: an urgency function replaces
the plain due-date sort behind the same call, so the UI doesn't change.
classify_urgency() (hub/models.py) is the stand-in for the weight-based
formula there until Item carries a real weight field.
"""
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from hub.models import classify_urgency

_URGENCY_ORDER = ("overdue", "critical", "high", "medium", "low")


def sort_items(rows, now=None):
    """Sort hub.db.upcoming() rows - (code, category, kind, title, due, url,
    done, source) - most urgent first. Ties break by due date."""

    def key(row):
        due = datetime.fromisoformat(row[4])
        return (_URGENCY_ORDER.index(classify_urgency(row[3], due, now)), due)

    return sorted(rows, key=key)


_COURSE_CODE_RE = re.compile(
    r"^(?P<faculty>[a-z]{2,5})[ _-]?[a-z]*[ _-]*"
    r"(?P<number>\d{2,4})[ _-]*(?P<section>\d{2,4})?",
    re.IGNORECASE,
)


def normalise_course_code(text):
    match = _COURSE_CODE_RE.match(text.strip())
    if not match:
        return None, None, None

    faculty = match.group("faculty").upper()
    number = match.group("number")
    section = match.group("section")
    return faculty, number, section


def delete_item(items, source, url):
    # Identity is (source, url) per AGENTS.md "Jacky's standard" - there's no
    # separate id field on Item.
    return [item for item in items if (item.source, item.url) != (source, url)]


def dedupe(items):
    seen = set()
    result = []
    for item in items:
        key = (item.course, item.title, item.due)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


_STOPWORDS = {"the", "a", "an", "of", "for", "to", "and", "on", "in", "at", "is", "-"}


def suspected_duplicates(items, title_threshold=0.6, due_tolerance=timedelta(hours=12)):
    """Cross-source pairs that look like the same task under a different name -
    e.g. the same assessment posted to both PrairieLearn and Canvas. Flags,
    doesn't merge: too risky to silently drop a real item on a fuzzy match, so
    this returns (canvas_item, other_item) pairs for the UI to show as
    "possible duplicate of ...", left for a human to resolve.

    # ponytail: title_threshold/due_tolerance are guesses, not tuned on real
    # Canvas/PrairieLearn data - adjust once we see actual cross-source pairs.
    Not wired into db.save() or app.py yet - logic only until UI direction lands.
    """
    flagged = []
    for a in items:
        if a.source != "canvas":
            continue
        for b in items:
            if b.source == "canvas" or a.due is None or b.due is None:
                continue
            if abs(a.due - b.due) > due_tolerance:
                continue
            if SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio() < title_threshold:
                continue
            a_words = {w for w in re.findall(r"\w+", a.title.lower())} - _STOPWORDS
            b_words = {w for w in re.findall(r"\w+", b.title.lower())} - _STOPWORDS
            if a_words & b_words:
                flagged.append((a, b))
    return flagged
