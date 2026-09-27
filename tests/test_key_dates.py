from hub.key_dates import fetch


def test_fetch_returns_a_course_and_dated_items():
    courses, items = fetch("UBCV")
    assert courses[0].code == "UBCV"
    assert len(items) >= 1
    assert all(item.due is not None for item in items)
    assert all(item.category == "deadline" for item in items)  # kind "payment" -> category_for -> "deadline"


def test_unknown_campus_returns_the_course_with_no_dates():
    courses, items = fetch("MARS_U")
    assert courses[0].code == "MARS_U"
    assert items == []


def test_items_have_distinct_urls_so_they_dont_collide_in_hub_db():
    # regression: two entries sharing a url would upsert onto the same
    # (source, url) identity in hub.db and silently overwrite each other.
    _, items = fetch("UBCV")
    urls = [item.url for item in items]
    assert len(urls) == len(set(urls))


def test_every_campus_shares_the_same_shape():
    from hub.key_dates import KEY_DATES
    for campus in KEY_DATES:
        courses, items = fetch(campus)
        assert courses[0].code == campus
        assert len(items) == len(KEY_DATES[campus])
