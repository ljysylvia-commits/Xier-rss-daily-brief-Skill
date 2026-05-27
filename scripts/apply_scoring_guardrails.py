#!/usr/bin/env python3
"""Apply deterministic post-Scorer guardrails to scored.json."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def lacks_content_evidence(cluster: dict[str, Any]) -> bool:
    return (
        int(cluster.get("primary_tokens") or 0) == 0
        and not cluster.get("rss_summary")
        and cluster.get("fetch_status") == "content_extraction_failed"
    )


def force_others(entry: dict[str, Any]) -> dict[str, Any]:
    updated = dict(entry)
    updated.update(
        {
            "base_score": 0.0,
            "cluster_bonus": 0.0,
            "non_consensus_bonus": 0.0,
            "stale_penalty": 0.0,
            "spam_penalty": 0.0,
            "final_score": 0.0,
            "tier": "others",
            "priority_reason": "原文抓取失败，缺少可用正文证据。",
            "match_mode": updated.get("match_mode") or "ai_discovered",
            "non_consensus_flag": False,
            "is_followup": False,
            "followup_ref_cluster": None,
            "spam_confidence": 0.0,
            "low_density_suspect": True,
            "risk_note": "中文摘要缺失",
        }
    )
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clusters-index", required=True, type=Path)
    parser.add_argument("--scored", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    clusters_index = load_json(args.clusters_index)
    scored = load_json(args.scored)
    forced_ids = {
        c.get("cluster_id")
        for c in clusters_index.get("clusters", [])
        if c.get("cluster_id") and lacks_content_evidence(c)
    }

    entries = []
    forced_count = 0
    for entry in scored.get("entries", []):
        if entry.get("cluster_id") in forced_ids:
            entries.append(force_others(entry))
            forced_count += 1
        else:
            entries.append(entry)

    out = dict(scored)
    out["entries"] = entries
    out.setdefault("meta", {})
    out["meta"]["scoring_guardrails"] = {
        "forced_content_extraction_failed_to_others": forced_count,
        "rule": "primary_tokens=0 && rss_summary=null && fetch_status=content_extraction_failed",
    }
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
