import re
from datetime import datetime, timezone

_NO_DUE_DATE = datetime.max.replace(tzinfo=timezone.utc)

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


def sort_items(items):
    return sorted(items, key=lambda item: item.due or _NO_DUE_DATE)
