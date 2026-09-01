"""{{filter}} tokens become SQL. Wrong expansion breaks every chart under a
filter; unescaped expansion is an injection hole."""
import pytest

from bizzmind import data


@pytest.fixture
def proj(fake_project, monkeypatch):
    p = fake_project(filters=[
        {"id": "countries", "type": "multi", "column": "Пазар", "label": "Пазар"},
        {"id": "metric", "type": "single", "column": "", "label": "Показател"},
    ])
    opts = {"metric": ["Оборот", "Количество (опаковки)"], "countries": ["Израел", "Либия"]}
    monkeypatch.setattr(data, "resolve_filter_options", lambda proj, f: opts.get(f["id"], []))
    return p


def test_multi_filter_expands_to_an_in_list(proj):
    out = data.apply_filters_to_sql(proj, "SELECT 1 FROM t WHERE {{countries}}", {"countries": ["Израел", "Либия"]})
    assert out == """SELECT 1 FROM t WHERE (CAST("Пазар" AS VARCHAR) IN ('Израел', 'Либия'))"""


def test_multi_filter_with_nothing_selected_is_true(proj):
    assert data.apply_filters_to_sql(proj, "WHERE {{countries}}", {}) == "WHERE TRUE"
    assert data.apply_filters_to_sql(proj, "WHERE {{countries}}", {"countries": []}) == "WHERE TRUE"


def test_quotes_in_selections_are_escaped_not_injected(proj):
    out = data.apply_filters_to_sql(proj, "WHERE {{countries}}", {"countries": ["O'Brien'); DROP TABLE t;--"]})
    assert "DROP TABLE" in out                      # it is data...
    assert out.count("'") % 2 == 0                  # ...and stays inside a closed literal
    assert "('O''Brien'');" in out


def test_unknown_token_becomes_true_rather_than_breaking_the_query(proj):
    assert data.apply_filters_to_sql(proj, "WHERE {{ghost}} AND 1=1", {"ghost": ["x"]}) == "WHERE TRUE AND 1=1"


def test_single_filter_substitutes_only_a_known_option(proj):
    assert data.apply_filters_to_sql(proj, "SELECT {{metric}}", {}) == "SELECT Оборот"
    assert data.apply_filters_to_sql(proj, "SELECT {{metric}}", {"metric": "Количество (опаковки)"}) == "SELECT Количество (опаковки)"
    # a value that is not one of the options is never spliced into SQL
    assert data.apply_filters_to_sql(proj, "SELECT {{metric}}", {"metric": "1; DROP TABLE t"}) == "SELECT Оборот"


def test_single_filter_without_options_yields_null(proj, monkeypatch):
    monkeypatch.setattr(data, "resolve_filter_options", lambda proj, f: [])
    assert data.apply_filters_to_sql(proj, "SELECT {{metric}}", {}) == "SELECT NULL"


def test_sql_without_tokens_is_untouched(proj):
    sql = 'SELECT "a" FROM "t" WHERE "b" = \'{{not a token because of the space}}\''
    assert data.apply_filters_to_sql(proj, sql, {}) == sql
