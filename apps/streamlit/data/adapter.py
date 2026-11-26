"""File-backed contract v1 adapters with no UI or pipeline dependency."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Protocol, TypedDict

import pandas as pd

COUNTS = ["total_events", "star_events", "fork_events", "push_events", "commits_pushed",
          "prs_opened", "prs_merged", "prs_closed_unmerged", "issues_opened",
          "issues_closed", "issue_comments", "unique_actors", "unique_human_actors",
          "active_contributors"]
KEYS = {"repository_registry": ["repository_id", "tracking_start_date"],
        "repository_metadata": ["repository_id", "snapshot_date"],
        "repository_daily_metrics": ["repository_id", "date"], "daily_data_status": ["date"]}


class Publication(TypedDict):
    contract_version: str
    data_source: str
    publication_id: str
    published_at: str
    expected_complete_through: str | None


class OverviewData(TypedDict):
    tracked_repositories: int
    totals: dict[str, int] | None
    trend: pd.DataFrame


class DataAdapter(Protocol):
    """One validated, consistent publication per adapter instance.

    Dates are inclusive UTC ISO dates. Returned frames/dicts are owned by callers;
    consumers may alter them without changing the publication. Catalog metadata
    is the latest observation, not an as-of historical classification.
    """
    def publication(self) -> Publication: ...
    def date_bounds(self) -> tuple[str, str] | None: ...
    def latest_complete_date(self) -> str | None: ...
    def day_status(self, start: str, end: str) -> pd.DataFrame: ...
    def repository_catalog(self) -> pd.DataFrame: ...
    def registry_history(self) -> pd.DataFrame: ...
    def overview(self, start: str, end: str) -> OverviewData: ...
    def list_repositories(self, query: str = "", offset: int = 0, limit: int = 20) -> pd.DataFrame: ...
    def repository_detail(self, repository_id: int) -> dict: ...
    def time_series(self, repository_id: int, start: str, end: str) -> pd.DataFrame: ...
    def growth_ranking(self, anchor: str, window: int = 30) -> pd.DataFrame: ...


class FixtureAdapter:
    source = "fixture"

    def __init__(self, directory: str | Path):
        root = Path(directory)
        self.envelope = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if self.envelope.get("data_source") != self.source:
            raise ValueError(f"{type(self).__name__} requires {self.source} source")
        if self.envelope.get("contract_version") != "1.0.0-draft":
            raise ValueError("Unsupported contract version")
        self.tables = {name: pd.read_parquet(root / f"{name}.parquet") for name in KEYS}
        self.validate()

    def validate(self):
        for name, keys in KEYS.items():
            frame = self.tables[name]
            if frame[keys].isna().any().any() or frame.duplicated(keys).any():
                raise ValueError(f"Invalid or duplicate key in {name}")
            if "repository_id" in frame and (frame.repository_id <= 0).any():
                raise ValueError("Repository IDs must be positive")
        registry = self.tables["repository_registry"]
        for _, group in registry.groupby("repository_id"):
            last_end = None
            for row in group.sort_values("tracking_start_date").itertuples():
                if last_end is not None and row.tracking_start_date <= last_end:
                    raise ValueError("Overlapping registry intervals")
                last_end = row.tracking_end_date or "9999-12-31"
        daily = self.tables["repository_daily_metrics"]
        statuses = self.tables["daily_data_status"]
        if not set(statuses.status) <= {"complete", "provisional", "missing"}:
            raise ValueError("Invalid day status")
        if ((statuses.expected_files != 24) | (statuses.processed_files < 0) | (statuses.processed_files > 24)).any():
            raise ValueError("Invalid file counts")
        complete = statuses.status == "complete"
        if ((statuses.loc[complete, "processed_files"] != 24).any()
                or not statuses.loc[complete, "quality_passed"].all()
                or statuses.loc[complete, "published_at"].isna().any()):
            raise ValueError("Complete day failed quality gates")
        if set(daily.date) - set(statuses.date):
            raise ValueError("Missing day status")
        for row in daily.itertuples():
            scope = registry[(registry.repository_id == row.repository_id)
                             & (registry.tracking_start_date <= row.date)
                             & (registry.tracking_end_date.fillna("9999-12-31") >= row.date)]
            if len(scope) != 1:
                raise ValueError("Daily row outside registry scope")
        # Every scoped repo/day must have a row, including missing and zero days.
        for row in statuses.itertuples():
            expected = set(registry[(registry.tracking_start_date <= row.date)
                                    & (registry.tracking_end_date.fillna("9999-12-31") >= row.date)].repository_id)
            if set(daily.loc[daily.date == row.date, "repository_id"]) != expected:
                raise ValueError("Daily coverage is not dense")
        for col in COUNTS:
            values = daily[col].dropna()
            if ((values < 0) | (values % 1 != 0)).any():
                raise ValueError(f"Invalid count {col}")
        joined = daily.merge(statuses[["date", "status"]], on="date", validate="many_to_one")
        required = [c for c in COUNTS if c not in {"commits_pushed", "active_contributors"}]
        if joined.loc[joined.status == "complete", required].isna().any().any():
            raise ValueError("Null required complete-day metric")
        if joined.loc[joined.status == "missing", COUNTS].notna().any().any():
            raise ValueError("Missing day must have null metrics")
        if ((daily.unique_human_actors > daily.unique_actors)
                | (daily.unique_actors > daily.total_events)).any():
            raise ValueError("Invalid actor counts")
        events = ["star_events", "fork_events", "push_events", "prs_opened", "prs_merged",
                  "prs_closed_unmerged", "issues_opened", "issues_closed", "issue_comments"]
        if (daily[events].sum(axis=1) > daily.total_events).any():
            raise ValueError("Event components exceed total")
        if set(self.tables["repository_metadata"].repository_id) - set(registry.repository_id):
            raise ValueError("Unknown metadata repository")

    def publication(self) -> Publication:
        return Publication(
            contract_version=self.envelope["contract_version"],
            data_source=self.envelope["data_source"],
            publication_id=self.envelope["publication_id"],
            published_at=self.envelope["published_at"],
            expected_complete_through=self.envelope.get("expected_complete_through"),
        )

    def date_bounds(self) -> tuple[str, str] | None:
        dates = self.tables["daily_data_status"].date
        return None if dates.empty else (dates.min(), dates.max())

    def latest_complete_date(self) -> str | None:
        statuses = self.tables["daily_data_status"]
        dates = statuses.loc[statuses.status == "complete", "date"]
        return None if dates.empty else dates.max()

    def day_status(self, start: str, end: str) -> pd.DataFrame:
        self._validate_range(start, end)
        rows = self.tables["daily_data_status"]
        return rows[rows.date.between(start, end)].sort_values("date").copy()

    @staticmethod
    def _validate_range(start: str, end: str) -> None:
        from datetime import date
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise ValueError("Start must precede end")

    def repository_catalog(self) -> pd.DataFrame:
        registry = self.tables["repository_registry"].sort_values("tracking_start_date").drop_duplicates("repository_id", keep="last").copy()
        metadata = self.tables["repository_metadata"].sort_values("observed_at").drop_duplicates("repository_id", keep="last")
        return registry.merge(metadata[["repository_id", "primary_language"]], on="repository_id", how="left", validate="one_to_one")

    def registry_history(self) -> pd.DataFrame:
        """All scope intervals, including ended intervals, for historical ML."""
        return self.tables["repository_registry"].sort_values(
            ["repository_id", "tracking_start_date"]
        ).copy()

    def overview(self, start: str, end: str) -> OverviewData:
        self._validate_range(start, end)
        registry = self.tables["repository_registry"]
        scoped = registry[(registry.tracking_start_date <= end)
                          & (registry.tracking_end_date.fillna("9999-12-31") >= start)]
        rows = self.tables["repository_daily_metrics"]
        rows = rows[rows.date.between(start, end)]
        statuses = self.tables["daily_data_status"]
        statuses = statuses[statuses.date.between(start, end)]
        expected = set(pd.date_range(start, end).strftime("%Y-%m-%d"))
        valid = set(statuses.date) == expected and (statuses.status == "complete").all()
        totals = None
        fields = ["total_events", "star_events", "fork_events"]
        if valid and not rows[fields].isna().any().any():
            totals = {field: int(rows[field].sum()) for field in fields}
            totals["active_repositories"] = int(rows.loc[rows.total_events > 0, "repository_id"].nunique())
        trend = rows.groupby("date")[fields].sum(min_count=1).reindex(sorted(expected))
        complete_dates = set(statuses.loc[statuses.status == "complete", "date"])
        trend.loc[~trend.index.isin(complete_dates), fields] = float("nan")
        # Complete days with no tracked activity are known zeros, not missing days.
        trend.loc[trend.index.isin(complete_dates), fields] = trend.loc[trend.index.isin(complete_dates), fields].fillna(0)
        return OverviewData(tracked_repositories=int(scoped.repository_id.nunique()), totals=totals,
                                trend=trend.rename_axis("date").reset_index())

    def list_repositories(self, query="", offset=0, limit=20):
        if offset < 0 or not 1 <= limit <= 1000:
            raise ValueError("Invalid pagination")
        frame = self.tables["repository_registry"].sort_values("tracking_start_date").drop_duplicates("repository_id", keep="last")
        frame = frame[frame.repository_name.str.contains(query, case=False, regex=False)]
        return frame.sort_values("repository_id").iloc[offset:offset + limit].copy()

    def repository_detail(self, repository_id):
        registry = self.tables["repository_registry"]
        rows = registry[registry.repository_id == repository_id].sort_values("tracking_start_date")
        if rows.empty:
            raise KeyError(repository_id)
        metadata = self.tables["repository_metadata"]
        snapshots = metadata[metadata.repository_id == repository_id].sort_values("observed_at")
        return deepcopy({"registry": rows.iloc[-1].to_dict(),
                         "metadata": None if snapshots.empty else snapshots.iloc[-1].to_dict()})

    def time_series(self, repository_id, start, end):
        self.repository_detail(repository_id)
        if pd.Timestamp(start) > pd.Timestamp(end):
            raise ValueError("Start must precede end")
        frame = self.tables["repository_daily_metrics"]
        return frame[(frame.repository_id == repository_id) & frame.date.between(start, end)].merge(
            self.tables["daily_data_status"], on="date", validate="many_to_one").sort_values("date").copy()

    def growth_ranking(self, anchor, window=30):
        if window not in {7, 30}:
            raise ValueError("Window must be 7 or 30")
        end = pd.Timestamp(anchor)
        start = end - pd.Timedelta(days=2 * window - 1)
        midpoint = (end - pd.Timedelta(days=window - 1)).strftime("%Y-%m-%d")
        result = []
        registry = self.tables["repository_registry"].sort_values("tracking_start_date").drop_duplicates("repository_id", keep="last")
        for repo in registry.itertuples():
            rows = self.time_series(repo.repository_id, start.strftime("%Y-%m-%d"), anchor)
            state = "valid"
            current = previous = delta = percent = None
            if len(rows) != 2 * window:
                state = "insufficient_history"
            elif (rows.status != "complete").any() or rows.star_events.isna().any():
                state = "incomplete_data"
            else:
                current = int(rows.loc[rows.date >= midpoint, "star_events"].sum())
                previous = int(rows.loc[rows.date < midpoint, "star_events"].sum())
                delta = current - previous
                if previous:
                    percent = 100 * delta / previous
                elif current:
                    state = "new_activity"
                else:
                    state, percent = "no_activity", 0.0
            result.append(dict(repository_id=repo.repository_id, repository_name=repo.repository_name,
                               current=current, previous=previous, absolute_delta=delta,
                               growth_pct=percent, state=state))
        return pd.DataFrame(result).sort_values(["current", "absolute_delta", "repository_id"],
                                                ascending=[False, False, True], na_position="last").reset_index(drop=True)


class SnapshotAdapter(FixtureAdapter):
    source = "snapshot"


def get_adapter(source="fixture", directory=None) -> DataAdapter:
    if source == "clickhouse_snapshot":
        from .clickhouse_snapshot import ClickHouseSnapshotAdapter
        from .config import ClickHouseConfig

        if not directory:
            raise ValueError("APP_SNAPSHOT_DIR is required for ClickHouse snapshot data")
        return ClickHouseSnapshotAdapter(directory, ClickHouseConfig.from_env())
    if source == "clickhouse":
        from .clickhouse_publication import ClickHousePublicationAdapter
        from .config import ClickHouseConfig
        return ClickHousePublicationAdapter(ClickHouseConfig.from_env())
    if source == "snapshot":
        if not directory:
            raise ValueError("APP_SNAPSHOT_DIR is required for snapshot data")
        return SnapshotAdapter(directory)
    if source != "fixture":
        raise ValueError("APP_DATA_SOURCE must be fixture, snapshot, clickhouse_snapshot or clickhouse")
    return FixtureAdapter(directory or Path(__file__).parent / "fixtures")
