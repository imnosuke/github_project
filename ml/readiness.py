"""ML-03 readiness diagnostics; never fit a model or certify external evidence."""
from datetime import date
import hashlib
import json

import pandas as pd

from apps.streamlit.data.adapter import COUNTS
from ml.features import build_dataset, days_between
from ml.spec import HORIZON_DAYS, LOOKBACK_DAYS, SPEC_VERSION

MIN_ANCHORS = {"train": 60, "validation": 30, "test": 30}
# Two purges and the final label horizon, with inclusive calendar endpoints.
MIN_CALENDAR_DAYS = LOOKBACK_DAYS + sum(MIN_ANCHORS.values()) + 3 * HORIZON_DAYS - 1
EXTERNAL_EVIDENCE = {
    "contract_confirmation": "DE confirms APP-02 version, schema, metric semantics and scope.",
    "gold_reconciliation": "APP-07 read-only serving and Gold reconciliation evidence.",
    "historical_availability": "Historical publication/decision availability or prospective snapshots, per ML-01.",
}


def base_report(config):
    return {
        "audit_version": 1, "spec_version": SPEC_VERSION,
        "config": config,
        "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "policy": {"minimum_distinct_anchor_dates": dict(MIN_ANCHORS),
                   "minimum_calendar_days": MIN_CALENDAR_DAYS,
                   "lookback_days": LOOKBACK_DAYS, "horizon_days": HORIZON_DAYS},
        "status": "blocked", "ready_for_ml03": False,
        "external_gates": {name: {"status": "unverified", "required_evidence": evidence}
                           for name, evidence in EXTERNAL_EVIDENCE.items()},
        "limitations": [
            "This audit does not verify DE approval, serving permissions, or historical availability.",
            "Passing calendar/eligibility checks is not evidence of model quality or statistical sufficiency.",
            "No training, tuning, prediction publishing, or automatic split changes are performed.",
        ],
    }


def input_error_report(config, category, message):
    report = base_report(config)
    report.update(data_status="unavailable" if category == "source_unavailable" else "invalid",
                  input_error={"category": category, "message": message},
                  blockers=[category, *EXTERNAL_EVIDENCE])
    return report


def grouped_counts(frame, column):
    return {str(key): int(value) for key, value in frame[column].value_counts().sort_index().items()}


def longest_complete_run(coverage):
    longest = current = 0
    for status in coverage.status:
        current = current + 1 if status == "complete" else 0
        longest = max(longest, current)
    return longest


def noncomplete_ranges(coverage):
    ranges = []
    for row in coverage.itertuples():
        if row.status == "complete":
            continue
        previous = ranges[-1] if ranges else None
        if (previous is not None and previous["status"] == row.status
                and (date.fromisoformat(row.date) - date.fromisoformat(previous["end"])).days == 1):
            previous["end"] = row.date
            previous["days"] += 1
        else:
            ranges.append({"start": row.date, "end": row.date, "status": row.status, "days": 1})
    return ranges


def label_summary(frame):
    if frame.empty:
        return {"rows": 0, "zero_fraction": None, "min": None,
                "median": None, "p90": None, "max": None}
    values = frame.target
    return {"rows": len(frame), "zero_fraction": float((values == 0).mean()),
            "min": int(values.min()), "median": float(values.median()),
            "p90": float(values.quantile(0.9)), "max": int(values.max())}


def readiness_report(data, config, days, split):
    """Return JSON-ready report plus diagnostic frames, from validated Inputs.

    Anchor minima count distinct eligible dates globally, never row counts.
    Per-repository coverage is separate; new repositories remain allowed.
    """
    report = base_report(config)
    coverage_rows = []
    for day in days_between(date.fromisoformat(data.lower), date.fromisoformat(data.upper)):
        tracked = [rid for rid in data.scope if data.in_scope(rid, day)]
        observed = sum((rid, day) in data.daily for rid in tracked)
        coverage_rows.append({"date": day, "status": data.statuses.get(day, "unknown"),
                              "tracked_repositories": len(tracked), "observed_repo_rows": observed,
                              "missing_repo_rows": len(tracked) - observed})
    coverage = pd.DataFrame(coverage_rows)
    samples, audit = build_dataset(data, days["anchor_start"], days["anchor_end"], split)
    split_summaries = {}
    for name, minimum in MIN_ANCHORS.items():
        frame = samples[samples.split == name]
        anchors = sorted(frame.anchor_date.unique())
        split_summaries[name] = {
            "rows": len(frame), "repositories": int(frame.repository_id.nunique()),
            "distinct_anchor_dates": len(anchors), "required_anchor_dates": minimum,
            "missing_anchor_dates_to_minimum": max(0, minimum - len(anchors)),
            "first_anchor": anchors[0] if anchors else None,
            "last_anchor": anchors[-1] if anchors else None,
            "labels": label_summary(frame),
        }
    repository_rows = []
    for rid in sorted(data.scope):
        eligible = samples[samples.repository_id == rid]
        reasons = audit[audit.repository_id == rid]
        row = {"repository_id": rid, "candidates": len(reasons), "kept_rows": len(eligible)}
        for name in MIN_ANCHORS:
            row[f"{name}_anchor_dates"] = int(eligible[eligible.split == name].anchor_date.nunique())
        row["excluded_rows"] = int((reasons.reason != "kept").sum())
        repository_rows.append(row)
    repositories = pd.DataFrame(repository_rows, columns=[
        "repository_id", "candidates", "kept_rows", "train_anchor_dates",
        "validation_anchor_dates", "test_anchor_dates", "excluded_rows",
    ])
    scoped_rows = int(coverage.tracked_repositories.sum())
    observed_rows = int(coverage.observed_repo_rows.sum())
    nulls = {metric: sum(row[metric] is None for row in data.daily.values()) for metric in COUNTS}
    zero_rows = sum(row["total_events"] == 0 for row in data.daily.values()
                    if row["total_events"] is not None and data.statuses.get(row["date"]) == "complete")
    lower_required = split.train_start.toordinal() - LOOKBACK_DAYS + 1
    upper_required = split.test_end.toordinal() + HORIZON_DAYS
    gates = {
        "input_validation": {"status": "passed"},
        "calendar_span": {"status": "passed" if len(coverage) >= MIN_CALENDAR_DAYS else "blocked",
                          "observed": len(coverage), "required": MIN_CALENDAR_DAYS},
        "configured_window": {
            "status": "passed" if date.fromisoformat(data.lower).toordinal() <= lower_required
            and date.fromisoformat(data.upper).toordinal() >= upper_required else "blocked",
            "required_start": date.fromordinal(lower_required).isoformat(),
            "required_end": date.fromordinal(upper_required).isoformat(),
        },
        **{f"{name}_anchors": {"status": "passed" if summary["missing_anchor_dates_to_minimum"] == 0 else "blocked",
                               "observed": summary["distinct_anchor_dates"], "required": MIN_ANCHORS[name]}
           for name, summary in split_summaries.items()},
    }
    structural_blockers = [name for name, gate in gates.items() if gate["status"] != "passed"]
    source_status = "passed" if data.publication["data_source"] == "live" else "blocked"
    report.update({
        "data_status": "passed" if not structural_blockers else "blocked",
        "data_gates": gates, "real_data_source": {"status": source_status, "observed": data.publication["data_source"]},
        "publication": data.publication, "input_fingerprint": data.fingerprint,
        "input_coverage": {"start": data.lower, "end": data.upper,
                           "calendar_days": len(coverage), "status_days": grouped_counts(coverage, "status"),
                           "longest_complete_run_days": longest_complete_run(coverage),
                           "noncomplete_ranges": noncomplete_ranges(coverage),
                           "scoped_repo_days": scoped_rows, "observed_repo_rows": observed_rows,
                           "missing_repo_rows": scoped_rows - observed_rows,
                           "observed_null_cells_by_metric": nulls,
                           "complete_zero_activity_repo_days": zero_rows},
        "eligibility": {"candidates": len(audit), "kept": len(samples),
                        "excluded": len(audit) - len(samples), "reason_counts": grouped_counts(audit, "reason")},
        "splits": split_summaries,
        "blockers": [*structural_blockers, *([] if source_status == "passed" else ["real_data_source"]),
                     *EXTERNAL_EVIDENCE],
    })
    if source_status != "passed":
        report["limitations"].insert(0, "SYNTHETIC FIXTURE: structural checks only, never real ML-03 readiness.")
    return report, {"coverage": coverage, "repository_coverage": repositories, "eligibility": audit}


def markdown_report(report):
    lines = ["# ML-03 readiness audit", "", f"Status: **{report['status']}**",
             f"Data checks: **{report['data_status']}**", "",
             f"Config SHA-256: `{report['config_sha256']}`", "", "## Blockers", ""]
    lines += [f"- `{name}`" for name in report["blockers"]]
    if "input_error" in report:
        lines += ["", "## Input error", "", report["input_error"]["message"]]
    else:
        coverage = report["input_coverage"]
        lines += ["", "## Input coverage", "",
                  f"Publication: `{report['publication']['publication_id']}` ({report['publication']['data_source']}).",
                  f"Range: {coverage['start']} to {coverage['end']}; {coverage['calendar_days']} calendar days.",
                  f"Status days: `{json.dumps(coverage['status_days'], sort_keys=True)}`.",
                  f"Missing scoped repo/day rows: {coverage['missing_repo_rows']}.", "",
                  f"Calendar span policy: at least {report['policy']['minimum_calendar_days']} days.",
                  f"Configured lookback/label coverage required: {report['data_gates']['configured_window']['required_start']} to {report['data_gates']['configured_window']['required_end']}.", "",
                  "## Eligible samples after purge", "",
                  "| Split | Rows | Repositories | Distinct anchors | Required anchors | Shortfall |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for name, summary in report["splits"].items():
            lines.append(f"| {name} | {summary['rows']} | {summary['repositories']} | {summary['distinct_anchor_dates']} | {summary['required_anchor_dates']} | {summary['missing_anchor_dates_to_minimum']} |")
        lines += ["", "## Eligibility audit", "",
                  f"Candidates: {report['eligibility']['candidates']}; kept: {report['eligibility']['kept']}; excluded: {report['eligibility']['excluded']}."]
        lines += [f"- `{reason}`: {count}" for reason, count in report["eligibility"]["reason_counts"].items()]
    lines += ["", "## Evidence still required", ""]
    lines += [f"- **{name}** (unverified): {gate['required_evidence']}" for name, gate in report["external_gates"].items()]
    lines += ["", "## Next steps", "",
              "- Review missing coverage and anchor shortfalls with DE before fixing the evaluation boundaries.",
              "- Complete APP-07 and reconcile Gold; fixtures cannot satisfy the real-data gate.",
              "- Record contract confirmation and availability evidence; this command does not verify them."]
    lines += ["", "## Limits", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"
