#!/usr/bin/env python3
"""Run lightweight contract checks for the open-source RSS Skill."""
from __future__ import annotations

import sys
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import apply_scoring_guardrails as guardrails  # noqa: E402
import build_other_signal_inputs as other_inputs  # noqa: E402
import fetch  # noqa: E402
import healthcheck  # noqa: E402
import render  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_raises(func, message: str) -> None:
    try:
        func()
    except ValueError:
        return
    raise AssertionError(message)


def test_no_evidence_guardrail() -> None:
    cluster = {
        "cluster_id": "c_no_evidence",
        "primary_tokens": 0,
        "rss_summary": None,
        "fetch_status": "content_extraction_failed",
    }
    require(guardrails.lacks_content_evidence(cluster), "no-evidence cluster should match guardrail")
    forced = guardrails.force_others(
        {"cluster_id": "c_no_evidence", "tier": "must_read", "final_score": 8.7}
    )
    require(forced["tier"] == "others", "no-evidence cluster should be forced to others")
    require(forced["final_score"] == 0.0, "no-evidence cluster should receive zero score")
    require(forced["risk_note"] == "中文摘要缺失", "no-evidence risk note should be fixed Chinese text")


def test_rss_summary_not_demoted() -> None:
    cluster = {
        "cluster_id": "c_summary_only",
        "primary_tokens": 0,
        "rss_summary": "本期播客摘要介绍了新产品发布、定价变化和后续路线图。",
        "fetch_status": "content_extraction_failed",
    }
    require(not guardrails.lacks_content_evidence(cluster), "rss_summary evidence must not be force-demoted")


def test_final_other_signal_coverage() -> None:
    scored = {
        "entries": [
            {"cluster_id": "c1", "tier": "must_read", "final_score": 100},
            {"cluster_id": "c2", "tier": "recommended", "final_score": 90},
            {"cluster_id": "c3", "tier": "recommended", "final_score": 80},
            {"cluster_id": "c4", "tier": "optional", "final_score": 70},
            {"cluster_id": "c5", "tier": "optional", "final_score": 60},
            {"cluster_id": "c6", "tier": "others", "final_score": 10},
        ]
    }
    value_mapped = {
        "entries": [
            {
                "meta": {"cluster_id": "c2"},
                "warnings": [{"type": "title_content_mismatch"}],
            }
        ]
    }
    report_config = {"report_length": {"max_must_read": 1, "max_recommended": 1, "max_optional": 1}}
    rows = other_inputs.final_other_signal_rows(scored, value_mapped, report_config)
    by_id = {row["cluster_id"]: row for row in rows}
    require(set(by_id) == {"c2", "c5", "c6"}, "final Other Signals coverage should include mismatch, cap, and original others")
    require(other_inputs.other_signal_reason(by_id["c2"]) == "auto_demoted_title_content_mismatch", "mismatch reason missing")
    require(other_inputs.other_signal_reason(by_id["c5"]) == "report_length_cap", "length-cap reason missing")
    require(other_inputs.other_signal_reason(by_id["c6"]) == "scored_others", "original others reason missing")


def test_other_signal_lint() -> None:
    clusters_index = {
        "clusters": [
            {
                "cluster_id": "c_other",
                "primary_tokens": 120,
                "rss_summary": "报告摘要",
                "fetch_status": "ok",
            }
        ]
    }
    bad = {"entries": [{"cluster_id": "c_other", "title_zh": "供应链成本上升", "gist_zh": "供应链成本上升"}]}
    expect_raises(
        lambda: render.validate_others_translated(bad, ["c_other"], clusters_index),
        "duplicated Other Signals gist should fail lint",
    )
    good = {
        "entries": [
            {
                "cluster_id": "c_other",
                "title_zh": "供应链成本上升",
                "gist_zh": "报告补充了运费、库存和交付周期变化，便于判断成本压力来源。",
            }
        ]
    }
    render.validate_others_translated(good, ["c_other"], clusters_index)


def test_warning_mapping() -> None:
    require(
        render.summarize_warnings([{"type": "source_uncertainty"}]) == "信源需核验",
        "source_uncertainty should map to 信源需核验",
    )
    require(
        render.summarize_warnings([{"type": "unknown_warning"}]) == "需人工复核",
        "unknown warning should map to 需人工复核",
    )


def test_unsupported_source_boundary() -> None:
    unsupported_urls = [
        "https://x.com/user/status/1",
        "https://twitter.com/user/status/1",
        "https://mobile.twitter.com/user/status/1",
        "https://nitter.net/user/status/1",
    ]
    for url in unsupported_urls:
        require(fetch.unsupported_url_type(url) == "x_twitter", f"fetch boundary missed {url}")
        require(healthcheck.unsupported_url_type(url) == "x_twitter", f"healthcheck boundary missed {url}")
    require(fetch.unsupported_url_type("https://example.com/story") is None, "normal URL should not be unsupported")

    source = fetch.Source(
        source_id="x_source",
        name="Unsupported Source",
        url="https://x.com/user",
        source_type="rss",
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("fetcher")
    logger.addHandler(handler)
    try:
        items = fetch.fetch_one(
            source,
            datetime.now(timezone.utc) - timedelta(days=1),
            datetime.now(timezone.utc),
            source_state={},
        )
    finally:
        logger.removeHandler(handler)
    require(items == [], "unsupported source should not produce raw items")
    require("unsupported_source_type=x_twitter" in stream.getvalue(), "unsupported source should be logged")

    source_state = fetch.annotate_freshness([], [source], datetime.now(timezone.utc))
    require(source_state["x_source"] == "unsupported", "unsupported source should not be marked no_new_items")


def main() -> int:
    tests = [
        test_no_evidence_guardrail,
        test_rss_summary_not_demoted,
        test_final_other_signal_coverage,
        test_other_signal_lint,
        test_warning_mapping,
        test_unsupported_source_boundary,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
