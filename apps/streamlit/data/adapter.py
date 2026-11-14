"""Fixture-backed contract v1 adapter; no UI or pipeline dependency."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import pandas as pd

COUNTS = ["total_events", "star_events", "fork_events", "push_events", "commits_pushed",
          "prs_opened", "prs_merged", "prs_closed_unmerged", "issues_opened",
          "issues_closed", "issue_comments", "unique_actors", "unique_human_actors",
          "active_contributors"]
KEYS = {"repository_registry": ["repository_id", "tracking_start_date"],
        "repository_metadata": ["repository_id", "snapshot_date"],
        "repository_daily_metrics": ["repository_id", "date"], "daily_data_status": ["date"]}


class DataAdapter(Protocol):
    def list_repositories(self, query: str = "", offset: int = 0, limit: int = 20) -> pd.DataFrame: ...
    def repository_detail(self, repository_id: int) -> dict: ...
    def time_series(self, repository_id: int, start: str, end: str) -> pd.DataFrame: ...
    def growth_ranking(self, anchor: str, window: int = 30) -> pd.DataFrame: ...


class FixtureAdapter:
    def __init__(self, directory: str | Path):
        root = Path(directory)
        self.envelope = json.loads((root / "manifest.json").read_text())
        if self.envelope.get("data_source") != "fixture":
            raise ValueError("Fixture adapter requires fixture source")
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
        return {"registry": rows.iloc[-1].to_dict(),
                "metadata": None if snapshots.empty else snapshots.iloc[-1].to_dict()}

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


def get_adapter(source="fixture", directory=None) -> DataAdapter:
    if source != "fixture":
        raise ValueError("Only fixture is implemented; live adapter is APP-07")
    return FixtureAdapter(directory or Path(__file__).parent / "fixtures")
