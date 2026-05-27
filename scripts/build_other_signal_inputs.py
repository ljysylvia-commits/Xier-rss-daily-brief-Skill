#!/usr/bin/env python3
"""Build deterministic evidence package for final Other Signals summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_REPORT_CONFIG = {
    "report_length": {
        "max_must_read": 3,
        "max_recommended": 5,
        "max_optional": 10,
    },
}

EVIDENCE_FIELDS = [
    "cluster_id",
    "primary_source_name",
    "source_channel_raw",
    "title",
    "primary_url",
    "rss_summary",
    "content_excerpt",
    "primary_tokens",
    "fetch_status",
    "fetch_error",
    "detail_fetch_status",
    "detail_fetch_error",
    "evidence_state",
    "content_warning",
]

TIER_LABEL = {
    "must_read": "必读",
    "recommended": "推荐",
    "optional": "可选",
    "others": "其他",
}


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_report_config(path: Path | None) -> dict[str, Any]:
    data = load_json(path)
    return deep_merge(DEFAULT_REPORT_CONFIG, data if isinstance(data, dict) else {})


def has_mismatch_warning(vm: dict[str, Any] | None) -> bool:
    for w in (vm or {}).get("warnings", []):
        wtype = w.get("type") if isinstance(w, dict) else str(w)
        if wtype == "title_content_mismatch":
            return True
    return False


def scored_by_id(scored: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        e.get("cluster_id"): e
        for e in scored.get("entries", [])
        if isinstance(e, dict) and e.get("cluster_id")
    }


def value_mapped_by_id(value_mapped: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not value_mapped:
        return {}
    return {
        (v.get("meta") or {}).get("cluster_id") or v.get("cluster_id"): v
        for v in value_mapped.get("entries", [])
        if isinstance(v, dict) and ((v.get("meta") or {}).get("cluster_id") or v.get("cluster_id"))
    }


def apply_auto_demotions(
    scored: dict[str, Any],
    value_mapped: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    vm_entries = value_mapped_by_id(value_mapped)
    rows: list[dict[str, Any]] = []
    for entry in scored.get("entries", []):
        cid = entry.get("cluster_id")
        if not cid:
            continue
        row = dict(entry)
        row["original_tier"] = row.get("original_tier") or row.get("tier")
        if has_mismatch_warning(vm_entries.get(cid)) and row.get("tier") != "others":
            row["tier"] = "others"
            row["auto_demoted_reason"] = "title_content_mismatch"
            row["original_tier_label"] = TIER_LABEL.get(row.get("original_tier"), row.get("original_tier"))
        rows.append(row)
    return rows


def project_display_tiers(rows: list[dict[str, Any]], report_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirror render.py rebalance_tiers so Step 4d covers final displayed Other Signals."""
    length_cfg = report_config.get("report_length") or {}
    caps = {
        "must_read": max(int(length_cfg.get("max_must_read", 3)), 0),
        "recommended": max(int(length_cfg.get("max_recommended", 5)), 0),
        "optional": max(int(length_cfg.get("max_optional", 10)), 0),
    }
    eligible: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for row in rows:
        item = {**row, "original_tier": row.get("original_tier") or row.get("tier")}
        if row.get("tier") in {"must_read", "recommended", "optional"}:
            eligible.append(item)
        else:
            item["tier"] = "others"
            others.append(item)

    eligible.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    out: list[dict[str, Any]] = []
    cursor = 0
    for tier in ("must_read", "recommended", "optional"):
        for item in eligible[cursor: cursor + caps[tier]]:
            new_item = {**item, "tier": tier}
            if new_item.get("original_tier") != tier:
                new_item["tier_adjusted_reason"] = "report_length_cap"
                new_item["original_tier_label"] = TIER_LABEL.get(
                    new_item.get("original_tier"), new_item.get("original_tier")
                )
            out.append(new_item)
        cursor += caps[tier]

    for item in eligible[cursor:]:
        new_item = {**item, "tier": "others", "tier_adjusted_reason": "report_length_cap"}
        new_item["original_tier_label"] = TIER_LABEL.get(new_item.get("original_tier"), new_item.get("original_tier"))
        others.append(new_item)

    return out + others


def final_other_signal_rows(
    scored: dict[str, Any],
    value_mapped: dict[str, Any] | None,
    report_config: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = apply_auto_demotions(scored, value_mapped)
    display_rows = project_display_tiers(rows, report_config)
    return [row for row in display_rows if row.get("tier") == "others" and row.get("cluster_id")]


def other_signal_reason(row: dict[str, Any]) -> str:
    if row.get("auto_demoted_reason") == "title_content_mismatch":
        return "auto_demoted_title_content_mismatch"
    if row.get("tier_adjusted_reason") == "report_length_cap":
        return "report_length_cap"
    return "scored_others"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clusters-index", required=True, type=Path)
    parser.add_argument("--scored", required=True, type=Path)
    parser.add_argument("--value-mapped", type=Path,
                        help="value_mapped.json；传入后会纳入 title_content_mismatch 自动降级条目")
    parser.add_argument("--report-config", type=Path, default=Path("./config/report_config.json"),
                        help="report_config.json；用于按 report_length 投影最终展示 tier")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    clusters_index = load_json(args.clusters_index)
    scored = load_json(args.scored)
    value_mapped = load_json(args.value_mapped) if args.value_mapped else None
    report_config = load_report_config(args.report_config)
    other_rows = final_other_signal_rows(scored, value_mapped, report_config)
    scored_entries = scored_by_id(scored)
    cluster_by_id = {
        c.get("cluster_id"): c
        for c in clusters_index.get("clusters", [])
        if c.get("cluster_id")
    }

    entries: list[dict[str, Any]] = []
    for row in other_rows:
        cid = row.get("cluster_id")
        cluster = cluster_by_id.get(cid)
        if not cluster:
            continue
        item = {field: cluster.get(field) for field in EVIDENCE_FIELDS}
        item["source_name"] = item.pop("primary_source_name")
        item["url"] = item.pop("primary_url")
        item["scorer_priority_reason"] = scored_entries.get(cid, {}).get("priority_reason")
        item["other_signal_reason"] = other_signal_reason(row)
        item["original_tier"] = row.get("original_tier")
        item["display_tier"] = "others"
        entries.append(item)

    out = {
        "entries": entries,
        "count": len(entries),
        "source": {
            "clusters_index": str(args.clusters_index),
            "scored": str(args.scored),
            "value_mapped": str(args.value_mapped) if args.value_mapped else None,
            "report_config": str(args.report_config) if args.report_config else None,
        },
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
