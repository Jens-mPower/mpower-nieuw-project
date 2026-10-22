from datetime import date

import pytest

from mpower_gsc import google_api


def test_default_period_is_28_days_ending_3_days_ago():
    assert google_api.default_period(date(2026, 10, 22)) == ("2026-09-22", "2026-10-19")


def test_build_query_body_with_defaults_and_filters():
    body = google_api.build_query_body(
        None, None, ["query", "page"], 100, 0, "web",
        [{"dimension": "page", "operator": "contains", "expression": "/blog/"}],
        today=date(2026, 10, 22),
    )
    assert body == {
        "startDate": "2026-09-22",
        "endDate": "2026-10-19",
        "dimensions": ["query", "page"],
        "rowLimit": 100,
        "startRow": 0,
        "type": "web",
        "dimensionFilterGroups": [{
            "groupType": "and",
            "filters": [{"dimension": "page", "operator": "contains", "expression": "/blog/"}],
        }],
    }


@pytest.mark.parametrize("kwargs, message", [
    ({"start_date": "22-10-2026"}, "JJJJ-MM-DD"),
    ({"start_date": "2026-10-10", "end_date": "2026-10-01"}, "na end_date"),
    ({"dimensions": ["keyword"]}, "Onbekende dimensie"),
    ({"search_type": "shopping"}, "search_type"),
    ({"row_limit": 30000}, "row_limit"),
    ({"filters": [{"dimension": "page"}]}, "filter"),
])
def test_build_query_body_validates_input(kwargs, message):
    args = dict(start_date=None, end_date=None, dimensions=["query"], row_limit=10,
                start_row=0, search_type="web", filters=None)
    args.update(kwargs)
    with pytest.raises(ValueError, match=message):
        google_api.build_query_body(**args)


def test_format_rows_maps_keys_and_converts_ctr_to_percent():
    rows = [{"keys": ["seo bureau", "https://x.nl/"], "clicks": 12, "impressions": 400,
             "ctr": 0.03, "position": 4.567}]
    assert google_api.format_rows(["query", "page"], rows) == [{
        "query": "seo bureau", "page": "https://x.nl/", "clicks": 12, "impressions": 400,
        "ctr_pct": 3.0, "position": 4.6,
    }]


def test_load_credentials_without_config_raises(monkeypatch):
    monkeypatch.delenv("GSC_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(google_api.ConfigError):
        google_api.load_credentials()


def test_load_credentials_missing_file_raises(monkeypatch):
    monkeypatch.delenv("GSC_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/bestaat/niet.json")
    with pytest.raises(google_api.ConfigError, match="bestaat niet"):
        google_api.load_credentials()
