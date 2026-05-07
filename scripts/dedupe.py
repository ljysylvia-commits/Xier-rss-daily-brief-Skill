#!/usr/bin/env python3
"""
Daily-Brief · Deduper
输入 raw_items.jsonl → 基于 simhash 把同主题条目聚成 cluster →
  ${RUN_DIR}/clusters/{cluster_id}.json · ${RUN_DIR}/clusters_index.json
规范见 ARCHITECTURE.md §2 数据契约
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from simhash import Simhash, SimhashIndex

SIMHASH_K = 3  # 海明距离阈值
TOKEN_RE = re.compile(r"[A-Za-z]+|[\u4e00-\u9fff]")


def tokens(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in TOKEN_RE.findall(text)]


def item_signature(item: dict[str, Any]) -> str:
    """用标题 + 正文前 1200 字做签名基础"""
    title = item.get("original_title") or ""
    body = (item.get("full_content") or "")[:1200]
    return f"{title}\n{body}"


def build_clusters(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    # 丢掉抓取失败且无内容的条目
    candidates = [i for i in items if i.get("full_content") or (i.get("fetch_status") == "ok")]

    hashes: list[tuple[str, Simhash]] = []
    for it in candidates:
        sh = Simhash(tokens(item_signature(it)))
        hashes.append((it["item_id"], sh))

    index = SimhashIndex(hashes, k=SIMHASH_K)

    # 并查集聚类
    parent: dict[str, str] = {iid: iid for iid, _ in hashes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for iid, sh in hashes:
        for dup in index.get_near_dups(sh):
            if dup != iid:
                union(iid, dup)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_id = {i["item_id"]: i for i in candidates}
    for iid in by_id:
        groups[find(iid)].append(by_id[iid])

    return list(groups.values())


def choose_primary(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    """优先 full_content_tokens 最多；并列时选 source_id 字典序最小。"""
    return sorted(
        cluster,
        key=lambda x: (-int(x.get("full_content_tokens") or 0), x.get("source_id", "")),
    )[0]


def summarize_cluster(cluster: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    primary = choose_primary(cluster)
    members = [x for x in cluster if x["item_id"] != primary["item_id"]]
    pub_list = sorted([x.get("published_at") for x in cluster if x.get("published_at")])
    earliest = pub_list[0] if pub_list else None
    latest = pub_list[-1] if pub_list else None

    cluster_id = f"c{idx:04d}"
    return {
        "cluster_id": cluster_id,
        "primary": primary,
        "members": members,
        "member_count": len(cluster),
        "distinct_sources": sorted({x["source_id"] for x in cluster}),
        "earliest_published_at": earliest,
        "latest_published_at": latest,
        "languages": sorted({x.get("lang", "unknown") for x in cluster}),
        "content_types": sorted({x.get("content_type", "other") for x in cluster}),
    }


def cluster_index_row(full: dict[str, Any]) -> dict[str, Any]:
    """给 Scorer 的精简元信息（不含 full_content）。"""
    p = full["primary"]
    return {
        "cluster_id": full["cluster_id"],
        "title": p.get("original_title"),
        "primary_source_id": p.get("source_id"),
        "primary_source_name": p.get("source_name"),
        "primary_url": p.get("source_url"),
        "content_type": p.get("content_type"),
        "language": p.get("lang"),
        "member_count": full["member_count"],
        "distinct_sources": full["distinct_sources"],
        "earliest_published_at": full["earliest_published_at"],
        "latest_published_at": full["latest_published_at"],
        "primary_tokens": int(p.get("full_content_tokens") or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args()

    items: list[dict[str, Any]] = []
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    groups = build_clusters(items)
    groups.sort(
        key=lambda g: max((x.get("published_at") or "") for x in g),
        reverse=True,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    for i, g in enumerate(groups, start=1):
        full = summarize_cluster(g, i)
        (args.output_dir / f"{full['cluster_id']}.json").write_text(
            json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        index_rows.append(cluster_index_row(full))

    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(
        json.dumps({"clusters": index_rows, "count": len(index_rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"clusters={len(index_rows)} index={args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
