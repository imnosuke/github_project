"""Consumers work against protocol methods, with no fixture internals."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from apps.streamlit.data import FixtureAdapter
from apps.streamlit.data.config import ClickHouseConfig
from apps.streamlit.data import get_adapter


class InterfaceOnlyAdapter:
    """Explicit public methods, intentionally no tables/envelope attributes."""
    def __init__(self, fixture):
        self.publication = fixture.publication
        self.date_bounds = fixture.date_bounds
        self.latest_complete_date = fixture.latest_complete_date
        self.day_status = fixture.day_status
        self.repository_catalog = fixture.repository_catalog
        self.registry_history = fixture.registry_history
        self.overview = fixture.overview
        self.list_repositories = fixture.list_repositories
        self.repository_detail = fixture.repository_detail
        self.time_series = fixture.time_series
        self.growth_ranking = fixture.growth_ranking


def test_pages_use_only_interface(monkeypatch):
    import apps.streamlit.data as data
    adapter = InterfaceOnlyAdapter(FixtureAdapter(Path(__file__).parents[1] / 'data/fixtures'))
    assert not hasattr(adapter, 'tables') and not hasattr(adapter, 'envelope')
    monkeypatch.setattr(data, 'get_adapter', lambda **kwargs: adapter)
    # Unique directory argument avoids cached adapters from other AppTest tests.
    monkeypatch.setenv('APP_FIXTURE_DIR', 'interface-only-test')
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'app.py')).run()
    for page in ['Overview', 'Repository Explorer', 'Growth Analytics']:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
    assert any('repo hợp lệ' in item.value for item in app.caption)


def test_adapter_result_frames_are_caller_owned():
    adapter = FixtureAdapter(Path(__file__).parents[1] / 'data/fixtures')
    frame = adapter.day_status('2026-11-01', '2026-11-01')
    frame.loc[:, 'status'] = 'missing'
    assert adapter.day_status('2026-11-01', '2026-11-01').iloc[0].status == 'complete'
    publication = adapter.publication()
    publication['publication_id'] = 'changed'
    assert adapter.publication()['publication_id'] != 'changed'
    metadata = adapter.repository_detail(1001)['metadata']
    original_topic = metadata['topics'][0]
    metadata['topics'][0] = 'changed'
    assert adapter.repository_detail(1001)['metadata']['topics'][0] == original_topic
    catalog = adapter.repository_catalog()
    catalog.loc[:, 'repository_name'] = 'changed'
    assert not adapter.repository_catalog().repository_name.eq('changed').any()
    overview = adapter.overview('2026-11-01', '2026-11-01')
    overview['trend'].loc[:, 'star_events'] = -1
    assert adapter.overview('2026-11-01', '2026-11-01')['trend'].star_events.ge(0).all()


def test_catalog_with_optional_empty_metadata():
    adapter = FixtureAdapter(Path(__file__).parents[1] / 'data/fixtures')
    adapter.tables['repository_metadata'] = adapter.tables['repository_metadata'].iloc[:0]
    adapter.validate()
    catalog = adapter.repository_catalog()
    assert len(catalog) == 6 and catalog.primary_language.isna().all()
    assert adapter.repository_detail(1001)['metadata'] is None


@pytest.mark.parametrize('method', ['day_status', 'overview'])
def test_adapter_rejects_reversed_range(method):
    adapter = FixtureAdapter(Path(__file__).parents[1] / 'data/fixtures')
    with pytest.raises(ValueError, match='Start must precede end'):
        getattr(adapter, method)('2026-11-02', '2026-11-01')


def test_clickhouse_config_and_secret_redaction():
    config = ClickHouseConfig.from_env({'APP_CLICKHOUSE_HOST': 'localhost', 'APP_CLICKHOUSE_PASSWORD': 'secret'})
    assert config.port == 8443 and config.secure
    assert config.password == 'secret' and 'secret' not in repr(config)
    assert ClickHouseConfig.from_env({'APP_CLICKHOUSE_HOST': 'localhost', 'APP_CLICKHOUSE_SECURE': 'false'}).port == 8123


@pytest.mark.parametrize('host', ['localhost', 'clickhouse.internal', '127.0.0.1', '::1', '2001:db8::1'])
def test_clickhouse_accepts_hostname_or_ip(host):
    assert ClickHouseConfig.from_env({'APP_CLICKHOUSE_HOST': host}).host == host


@pytest.mark.parametrize('key,value', [
    ('HOST', ''), ('HOST', 'https://user:secret@localhost'), ('PORT', '0'),
    ('HOST', 'localhost:8123'), ('HOST', '[::1]:8123'), ('HOST', '-invalid'),
    ('HOST', 'bad..host'), ('HOST', 'bad\\host'),
    ('PORT', '65536'), ('PORT', 'oops'), ('SECURE', 'yes'),
    ('CONNECT_TIMEOUT', '0'), ('QUERY_TIMEOUT', 'nan'), ('QUERY_TIMEOUT', 'inf'),
    ('QUERY_TIMEOUT', 'secret'), ('USER', ''), ('DATABASE', ''),
])
def test_invalid_clickhouse_config(key, value):
    with pytest.raises(ValueError) as exc:
        ClickHouseConfig.from_env({'APP_CLICKHOUSE_HOST': 'localhost', 'APP_CLICKHOUSE_' + key: value})
    assert 'secret' not in str(exc.value)


def test_clickhouse_source_does_not_fall_back(monkeypatch):
    monkeypatch.setenv('APP_CLICKHOUSE_HOST', 'localhost')
    from apps.streamlit.data import clickhouse_publication
    monkeypatch.setattr(clickhouse_publication, "read_rows", lambda *_, **__: [])
    with pytest.raises(OSError, match="no committed APP-02 publication"):
        get_adapter("clickhouse")
    with pytest.raises(ValueError, match='APP_DATA_SOURCE'):
        get_adapter('unknown')


def test_clickhouse_snapshot_rejects_gold_metric_mismatch(monkeypatch):
    from apps.streamlit.data.clickhouse_snapshot import ClickHouseSnapshotAdapter

    directory = Path(__file__).resolve().parents[1] / 'data/snapshots/gharchive-2025-01-15'
    reference = get_adapter('snapshot', directory)
    rows = reference.tables['repository_daily_metrics'].to_dict('records')
    monkeypatch.setenv('APP_CLICKHOUSE_HOST', 'localhost')
    monkeypatch.setattr(ClickHouseSnapshotAdapter, 'read_gold', staticmethod(lambda *_: rows))

    gold = get_adapter('clickhouse_snapshot', directory)
    assert gold.overview('2025-01-15', '2025-01-15')['totals']['total_events'] == 516

    rows[0]['star_events'] -= 1
    with pytest.raises(ValueError, match='Gold metrics do not match'):
        get_adapter('clickhouse_snapshot', directory)

def test_clickhouse_snapshot_rejects_null_required_pr_counts(monkeypatch):
    from apps.streamlit.data.clickhouse_snapshot import ClickHouseSnapshotAdapter

    directory = Path(__file__).resolve().parents[1] / "data/snapshots/gharchive-2025-01-15"
    rows = get_adapter("snapshot", directory).tables["repository_daily_metrics"].to_dict("records")
    rows[0].update(prs_merged=None, prs_closed_unmerged=None)
    monkeypatch.setenv("APP_CLICKHOUSE_HOST", "localhost")
    monkeypatch.setattr(ClickHouseSnapshotAdapter, "read_gold", staticmethod(lambda *_: rows))

    with pytest.raises(ValueError, match="Gold metrics do not match"):
        get_adapter("clickhouse_snapshot", directory)
