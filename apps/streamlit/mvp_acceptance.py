"""Exercise the MVP in AppTest and print APP-11 acceptance evidence as JSON."""

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from time import perf_counter

from streamlit.testing.v1 import AppTest

from apps.streamlit.acceptance import METRICS, check_publication
from apps.streamlit.analytics import OVERVIEW_METRICS
from apps.streamlit.data import get_adapter


APP = Path(__file__).with_name("app.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_ui(adapter, anchor, incomplete_day, timeout):
    timings = {}
    bounds = adapter.date_bounds()
    require(bounds is not None, "The publication contains no dated rows")
    lower, upper = bounds
    require(lower <= anchor.isoformat() <= upper, "The Growth anchor falls outside the publication")
    if incomplete_day is not None:
        require(lower <= incomplete_day.isoformat() <= upper, "The incomplete day falls outside the publication")

    def run(widget, label):
        start = perf_counter()
        widget.run(timeout=timeout)
        timings[label] = round(perf_counter() - start, 3)
        require(not app.exception and not app.error, f"UI reported an error during {label}")

    app = AppTest.from_file(str(APP), default_timeout=timeout)
    run(app, "initial_render")
    publication = adapter.publication()
    captions = {item.value for item in app.sidebar.caption}
    require(f"Bản dữ liệu · {publication['publication_id']}" in captions and
            f"Nguồn dữ liệu · {publication['data_source']}" in captions,
            "UI loaded a different publication from the acceptance check")

    dates = (anchor, anchor)
    run(app.sidebar.date_input(key="date_range").set_value(dates), "overview")
    day = anchor.isoformat()
    totals = adapter.overview(day, day)["totals"]
    displayed = {metric.label: metric.value for metric in app.metric}
    require(totals is not None and all(displayed.get(label) == f"{totals[field]:,}"
                                     for field, label in OVERVIEW_METRICS.items()),
            "Overview did not display the accepted event, star and fork totals")

    run(app.sidebar.radio(key="page").set_value("Repository Explorer"), "explorer")
    repo = app.selectbox(key="detail_repo")
    require(repo.value is not None, "Explorer did not open a repository")
    comparison = len(repo.options) > 1
    if comparison:
        other = app.selectbox(key="compare_repo").value
        run(repo.set_value(other), "explorer_change_repository")
        require(app.selectbox(key="detail_repo").value == other, "Explorer did not switch repository")
        require(app.selectbox(key="compare_repo").value != other, "Explorer compared a repository with itself")

    run(app.sidebar.radio(key="page").set_value("Growth Analytics"), "growth")
    require(app.sidebar.date_input(key="date_range").value == dates, "Growth lost the shared date range")
    expected = adapter.growth_ranking(day, 30)
    eligible = int(expected[["current", "previous"]].notna().all(axis=1).sum())
    require(eligible > 0 and any(item.value == f"{eligible}/{len(expected)} repo đủ dữ liệu" for item in app.caption),
            "Growth did not display the eligible repositories for the 30-day comparison")

    if incomplete_day is not None:
        day = incomplete_day.isoformat()
        require(adapter.overview(day, day)["totals"] is None, "The selected incomplete day is complete")
        run(app.sidebar.radio(key="page").set_value("Overview"), "return_to_overview")
        run(app.sidebar.date_input(key="date_range").set_value((incomplete_day, incomplete_day)), "incomplete_day")
        displayed = {metric.label: metric.value for metric in app.metric}
        require(all(displayed.get(label) == "—" for label in OVERVIEW_METRICS.values()),
                "Overview exposed event totals on an incomplete day")
        require(any("chưa complete" in item.value for item in app.warning),
                "Overview did not explain why totals are unavailable")

    return {
        "overview_totals": {field: totals[field] for field in METRICS},
        "explorer_comparison": "passed" if comparison else "skipped_single_repository",
        "growth_eligible_repositories": eligible,
        "incomplete_day": incomplete_day.isoformat() if incomplete_day else None,
        "render_seconds": timings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("fixture", "clickhouse"), required=True)
    parser.add_argument("--anchor", type=date.fromisoformat)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-day", type=date.fromisoformat)
    parser.add_argument("--incomplete-day", type=date.fromisoformat)
    parser.add_argument("--ui-timeout", type=int, default=60)
    args = parser.parse_args(argv)
    if args.ui_timeout <= 0:
        parser.error("--ui-timeout must be positive")
    if args.source == "clickhouse" and not (args.anchor and args.reference and args.reference_day):
        parser.error("ClickHouse requires --anchor, --reference and --reference-day")
    if args.source == "fixture" and (args.reference or args.reference_day):
        parser.error("--reference and --reference-day apply to ClickHouse")

    anchor = args.anchor or date(2026, 10, 31)
    incomplete_day = args.incomplete_day
    directory = os.environ.get("APP_FIXTURE_DIR") if args.source == "fixture" else None
    if args.source == "fixture" and not directory and incomplete_day is None:
        incomplete_day = date(2026, 11, 3)
    previous_source = os.environ.get("APP_DATA_SOURCE")
    os.environ["APP_DATA_SOURCE"] = args.source
    report = {"source": args.source, "checked_at": datetime.now(timezone.utc).isoformat(),
              "growth_anchor": anchor.isoformat(), "passed": False}
    try:
        start = perf_counter()
        adapter = get_adapter(args.source, directory)
        report["publication_load_seconds"] = round(perf_counter() - start, 3)
        report["publication"] = adapter.publication()
        if args.source == "clickhouse":
            report["reference_metrics"] = check_publication(adapter, get_adapter("snapshot", args.reference),
                                                            args.reference_day, anchor)
            require(report["reference_metrics"]["passed"], "APP-07 reconciliation did not pass")
        report["ui"] = check_ui(adapter, anchor, incomplete_day, args.ui_timeout)
        report["passed"] = True
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        report["error"] = str(exc)
    finally:
        if previous_source is None:
            os.environ.pop("APP_DATA_SOURCE", None)
        else:
            os.environ["APP_DATA_SOURCE"] = previous_source
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
