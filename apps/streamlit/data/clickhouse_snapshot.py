"""Read a single-day Gold snapshot and reconcile it against its APP-02 evidence."""

import json
from ipaddress import ip_address

import pandas as pd

from .adapter import COUNTS, SnapshotAdapter
from .config import ClickHouseConfig
from .clickhouse_http import read_rows


GOLD_QUERY = """
SELECT repo_id AS repository_id, toString(event_date) AS date,
       total_events, stars_gained AS star_events, forks_count AS fork_events,
       push_events_count AS push_events, total_commits_pushed AS commits_pushed,
       prs_opened, prs_merged, prs_closed_unmerged, issues_opened, issues_closed,
       issue_comments_count AS issue_comments, unique_contributors AS unique_actors,
       unique_human_contributors AS unique_human_actors,
       CAST(NULL AS Nullable(Int64)) AS active_contributors
FROM {database:Identifier}.gold_repo_daily_activity
WHERE event_date = {day:Date} AND repo_id IN {scope:Array(Int64)}
ORDER BY repository_id
LIMIT {row_limit:UInt64}
FORMAT JSONEachRow
"""


class ClickHouseSnapshotAdapter(SnapshotAdapter):
    def __init__(self, directory, config):
        super().__init__(directory)
        statuses = self.tables["daily_data_status"]
        expected = self.tables["repository_daily_metrics"]
        if len(statuses) != 1 or statuses.iloc[0].status != "complete" or expected.empty:
            raise ValueError("ClickHouse snapshot requires one complete day with a nonempty repo scope")

        columns = ["repository_id", "date", *COUNTS]
        reference = expected[columns].sort_values("repository_id").reset_index(drop=True)
        scope = reference.repository_id.tolist()
        data = self.read_gold(config, statuses.iloc[0].date, scope)
        if len(data) != len(reference) or any(set(row) != set(columns) for row in data):
            raise ValueError("ClickHouse Gold rows do not match the snapshot schema or scope")
        actual = pd.DataFrame.from_records(data, columns=columns)
        # ClickHouse may serialize 64-bit integers as JSON strings.
        for column in ["repository_id", *COUNTS]:
            actual[column] = pd.to_numeric(actual[column], errors="raise").astype("Int64")
        try:
            pd.testing.assert_frame_equal(actual, reference, check_dtype=False)
        except AssertionError:
            raise ValueError("ClickHouse Gold metrics do not match the snapshot evidence") from None
        self.tables["repository_daily_metrics"] = actual
        self.validate()

    @staticmethod
    def read_gold(config: ClickHouseConfig, day, scope):
        if config.host != "localhost" and not _is_loopback(config.host):
            raise ValueError("ClickHouse snapshot requires a local loopback host")
        return read_rows(config, GOLD_QUERY, {
            "database": config.database, "day": day, "scope": json.dumps(scope),
            "row_limit": len(scope) + 1,
        }, row_limit=len(scope))


def _is_loopback(host):
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
