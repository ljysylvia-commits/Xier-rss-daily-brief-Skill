#!/usr/bin/env python3
"""
merge_perspectives.py — Value-Mapper · Step 4c

将 Reader VM 产物（${RUN_DIR}/value_mapped_reader/{cid}.json）
与 Audience VM 产物（${RUN_DIR}/value_mapped_audience/{cid}.json）
合并为单 cluster 合并体，再聚合为 ${RUN_DIR}/value_mapped.json。

职责：
  1. 字段归并：Reader 产 base 字段（title_zh / key_tags / core_content / reading_suggestion）
               + Reader 视角 value_blocks；Audience 产 audience 视角 value_blocks + pillars
  2. Dedup 二次终审：对每对 (reader_block, audience_block) 做相似度计算，>= 阈值视为重复，
                     audience 侧直接 drop，记录到 skipped_perspectives（中文原因）
  3. Lint：
      - perspective ∈ {"reader", "audience"}
      - angle key 在各自视角的枚举集合内
      - body 40-110 中文字
      - 禁用词黑名单
      - Reader 不得出现 pillars
      - Audience 不得出现 base 字段
  4. 合并输出 ${RUN_DIR}/value_mapped.json，结构见 value-mapper-schema.md §1.3

命令行用法：
  python3 scripts/merge_perspectives.py \
    --reader-dir "${RUN_DIR}/value_mapped_reader" \
    --audience-dir "${RUN_DIR}/value_mapped_audience" \
    --scored "${RUN_DIR}/scored.json" \
    --output "${RUN_DIR}/value_mapped.json" \
    --dedup-threshold 0.72
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ----- 枚举与约束（angle_config.json 是 Reader/Audience angle 单一真相源） -----

READER_ANGLE_KEYS = {
    "decision_impact",
    "context_shift",
    "cognitive_framework",
    "workflow_action",
    "system_or_product_signal",
    "firsthand_evidence",
    "risk_or_constraint",
    "counter_consensus",
}

AUDIENCE_ANGLE_KEYS = {
    "practical_application",
    "cognitive_update",
    "role_or_workflow_change",
    "efficiency_or_quality",
    "cost_or_resource",
    "structural_impact",
    "strategic_choice",
}

# 禁用词黑名单（ARCHITECTURE.md §4 不变量 #7）
BANNED_PHRASES = [
    "值得关注",
    "意义重大",
    "反思了",
    "做出了重大",
    "具有深远",
    "十分重要",
    "带来了根本性",
]

BODY_MIN_CHARS = 28
BODY_MAX_CHARS = 110
CONTENT_MODES = {"single_article", "roundup_digest", "transcript_long", "sparse_short"}


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_angle_config(path: Path | None) -> tuple[set[str], set[str], dict[str, str], dict[str, str]]:
    """读取 Reader/Audience angle key 与中文 label；缺失时回退到内置默认。"""
    if path is None or not path.exists():
        return set(READER_ANGLE_KEYS), set(AUDIENCE_ANGLE_KEYS), dict(READER_ANGLE_CN), dict(AUDIENCE_ANGLE_CN)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set(READER_ANGLE_KEYS), set(AUDIENCE_ANGLE_KEYS), dict(READER_ANGLE_CN), dict(AUDIENCE_ANGLE_CN)

    def collect(section: str, fallback_keys: set[str], fallback_labels: dict[str, str]) -> tuple[set[str], dict[str, str]]:
        keys: set[str] = set()
        labels: dict[str, str] = {}
        for item in data.get(section, []) or []:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not key:
                continue
            keys.add(str(key))
            labels[str(key)] = str(item.get("label_zh") or key)
        return (keys or set(fallback_keys), labels or dict(fallback_labels))

    reader_keys, reader_labels = collect("reader", READER_ANGLE_KEYS, READER_ANGLE_CN)
    audience_keys, audience_labels = collect("audience", AUDIENCE_ANGLE_KEYS, AUDIENCE_ANGLE_CN)
    return reader_keys, audience_keys, reader_labels, audience_labels


def cn_char_count(s: str) -> int:
    """统计中文字符数（近似 body 长度口径）。"""
    if not s:
        return 0
    return len([c for c in s if "\u4e00" <= c <= "\u9fff"])


def tokenize_for_sim(s: str) -> set[str]:
    """最小化分词：中文 bigram + ASCII 词汇。用于 Jaccard 相似度。"""
    if not s:
        return set()
    s = s.lower()
    tokens: set[str] = set()
    # 中文 bigram
    chinese = "".join(c for c in s if "\u4e00" <= c <= "\u9fff")
    for i in range(len(chinese) - 1):
        tokens.add(chinese[i:i + 2])
    # ASCII 词
    for w in re.findall(r"[a-z0-9]+", s):
        if len(w) >= 2:
            tokens.add(w)
    return tokens


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def similarity(a: str, b: str) -> float:
    return jaccard(tokenize_for_sim(a), tokenize_for_sim(b))


def lint_block(
    block: dict[str, Any],
    expected_perspective: str,
    allowed_angles: set[str],
    warnings: list[dict[str, Any]],
    where: str,
) -> bool:
    """返回 True = 通过 lint；False = fail（调用方应 drop）。"""
    ok = True
    p = block.get("perspective")
    if p != expected_perspective:
        warnings.append({"type": "lint_fail", "where": where, "reason": f"perspective 应为 {expected_perspective}，实为 {p!r}"})
        ok = False
    angle = block.get("angle")
    if angle not in allowed_angles:
        warnings.append({"type": "lint_fail", "where": where, "reason": f"angle {angle!r} 不在 {expected_perspective} 枚举集"})
        ok = False
    body = block.get("body", "")
    n = cn_char_count(body)
    if n < BODY_MIN_CHARS or n > BODY_MAX_CHARS:
        warnings.append({"type": "lint_fail", "where": where, "reason": f"body 中文字数 {n} 超出 {BODY_MIN_CHARS}-{BODY_MAX_CHARS}"})
        ok = False
    for bad in BANNED_PHRASES:
        if bad in body:
            warnings.append({"type": "lint_fail", "where": where, "reason": f"body 命中禁用词 {bad!r}"})
            ok = False
            break
    return ok


def lint_reader_contract(reader_vm: dict[str, Any] | None, warnings: list[dict[str, Any]]) -> None:
    """Lint Reader VM base fields that are not value_blocks.

    These checks intentionally warn instead of dropping the entry. Their goal is
    to catch coverage risks such as long digest content being summarized from
    the opening paragraph only.
    """
    if not reader_vm:
        return

    mode = reader_vm.get("content_mode")
    if not mode:
        warnings.append({
            "type": "missing_content_mode",
            "where": "reader_vm",
            "reason": "Reader VM 必须产出 content_mode",
        })
        return
    if mode not in CONTENT_MODES:
        warnings.append({
            "type": "invalid_content_mode",
            "where": "reader_vm",
            "reason": f"content_mode {mode!r} 不在枚举集 {sorted(CONTENT_MODES)}",
        })
        return

    if mode != "roundup_digest":
        return

    section_scan = reader_vm.get("section_scan")
    if not isinstance(section_scan, list) or not section_scan:
        warnings.append({
            "type": "missing_section_scan",
            "where": "reader_vm",
            "reason": "roundup_digest 必须产出 section_scan",
        })
        return

    if len(section_scan) < 3:
        warnings.append({
            "type": "insufficient_section_scan",
            "where": "reader_vm",
            "reason": f"roundup_digest 的 section_scan 只有 {len(section_scan)} 条，少于 3 条",
        })

    selected = [s for s in section_scan if isinstance(s, dict) and s.get("selection_decision") == "selected"]
    if not selected:
        warnings.append({
            "type": "no_selected_section",
            "where": "reader_vm",
            "reason": "roundup_digest 的 section_scan 至少需要 1 条 selected section",
        })

    core_content = reader_vm.get("core_content") or []
    first_core = core_content[0] if core_content else ""
    has_coverage_statement = (
        ("多主题" in first_core or "聚合" in first_core or "digest" in first_core.lower())
        and ("本日报" in first_core or "选取" in first_core or "选择" in first_core or "主线" in first_core)
    )
    if not has_coverage_statement:
        warnings.append({
            "type": "coverage_statement_missing",
            "where": "reader_vm.core_content[0]",
            "reason": "roundup_digest 的 core_content 第一条应说明多主题聚合及本日报选取的主线",
        })

    for idx, item in enumerate(core_content):
        if isinstance(item, str) and "摘要提到" in item:
            warnings.append({
                "type": "source_wording_risk",
                "where": f"reader_vm.core_content[{idx}]",
                "reason": "roundup_digest 已读 full_content 时不应笼统写“摘要提到”；应说明来自正文 section 或该 issue 的主线",
            })


def merge_single(
    reader_vm: dict[str, Any] | None,
    audience_vm: dict[str, Any] | None,
    cid: str,
    dedup_threshold: float,
    reader_angle_keys: set[str],
    audience_angle_keys: set[str],
    reader_angle_labels: dict[str, str],
    audience_angle_labels: dict[str, str],
) -> dict[str, Any]:
    """合并一个 cluster 的 Reader + Audience 产物；返回合并后的对象。"""
    warnings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    # base 字段归 Reader
    merged: dict[str, Any] = {
        "meta": {
            "cluster_id": cid,
            "reader_model": (reader_vm or {}).get("meta", {}).get("model"),
            "audience_model": (audience_vm or {}).get("meta", {}).get("model"),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "title_zh": (reader_vm or {}).get("title_zh") or "",
        "key_tags": (reader_vm or {}).get("key_tags") or [],
        "content_mode": (reader_vm or {}).get("content_mode") or "",
        "section_scan": (reader_vm or {}).get("section_scan") or [],
        "core_content": (reader_vm or {}).get("core_content") or [],
        "reading_suggestion": (reader_vm or {}).get("reading_suggestion") or "",
        "value_blocks": [],
        "pillars": [],
        "skipped_perspectives": [],
        "warnings": [],
    }

    # ---- Reader value_blocks ----
    lint_reader_contract(reader_vm, warnings)
    reader_blocks_raw = (reader_vm or {}).get("value_blocks") or []
    reader_blocks: list[dict[str, Any]] = []
    for idx, b in enumerate(reader_blocks_raw):
        if lint_block(b, "reader", reader_angle_keys, warnings, where=f"reader[{idx}]"):
            reader_blocks.append(b)
    # Reader 透传 skipped_perspectives（若 VM 输出了）
    for sp in (reader_vm or {}).get("skipped_perspectives", []) or []:
        skipped.append(sp)

    # ---- Audience value_blocks + dedup 终审 ----
    audience_blocks_raw = (audience_vm or {}).get("value_blocks") or []
    audience_blocks: list[dict[str, Any]] = []
    for idx, b in enumerate(audience_blocks_raw):
        if not lint_block(b, "audience", audience_angle_keys, warnings, where=f"audience[{idx}]"):
            continue
        # dedup 二次终审
        a_body = b.get("body", "")
        hit_sim: float | None = None
        hit_angle_cn: str | None = None
        for rb in reader_blocks:
            sim = similarity(a_body, rb.get("body", ""))
            if sim >= dedup_threshold:
                hit_sim = sim
                hit_angle_cn = reader_angle_cn(rb.get("angle", ""), reader_angle_labels)
                break
        if hit_sim is not None:
            skipped.append({
                "视角": f"audience · {audience_angle_cn(b.get('angle', ''), audience_angle_labels)}",
                "原因": f"与 Reader「{hit_angle_cn}」内容高度重合（相似度 {hit_sim:.2f}）",
            })
            continue
        audience_blocks.append(b)
    # Audience 透传 skipped_perspectives
    for sp in (audience_vm or {}).get("skipped_perspectives", []) or []:
        skipped.append(sp)

    # Audience 禁止携带 base 字段：lint 仅作 warning，不覆盖
    for bad_field in ("title_zh", "key_tags", "core_content", "reading_suggestion"):
        if (audience_vm or {}).get(bad_field):
            warnings.append({
                "type": "lint_fail",
                "where": "audience_vm",
                "reason": f"Audience VM 不应产出 base 字段 {bad_field!r}（已忽略）",
            })

    # ---- pillars 归 Audience ----
    pillars = (audience_vm or {}).get("pillars") or []
    if isinstance(pillars, list) and len(pillars) <= 2:
        merged["pillars"] = pillars
    else:
        warnings.append({"type": "lint_fail", "where": "audience_vm", "reason": f"pillars 数量 {len(pillars)} 超过 0-2；已截断"})
        merged["pillars"] = pillars[:2] if isinstance(pillars, list) else []

    # Reader 不得携带 pillars
    if (reader_vm or {}).get("pillars"):
        warnings.append({
            "type": "lint_fail",
            "where": "reader_vm",
            "reason": "Reader VM 不应产出 pillars（已忽略）",
        })

    # ---- 合并 value_blocks（reader 在前，audience 在后） ----
    merged["value_blocks"] = reader_blocks + audience_blocks
    merged["skipped_perspectives"] = skipped
    # 合并 warnings：Reader + Audience 透传 + 本地 lint
    for src_vm in (reader_vm, audience_vm):
        for w in (src_vm or {}).get("warnings", []) or []:
            if w not in merged["warnings"]:
                merged["warnings"].append(w)
    for w in warnings:
        if w not in merged["warnings"]:
            merged["warnings"].append(w)

    return merged


# ---- angle key → 中文名（供 skipped_perspectives 渲染，不走 Writer） ----

READER_ANGLE_CN = {
    "decision_impact": "决策影响",
    "context_shift": "背景变化",
    "cognitive_framework": "认知框架",
    "workflow_action": "行动方法",
    "system_or_product_signal": "系统/产品信号",
    "firsthand_evidence": "一手证据",
    "risk_or_constraint": "风险与约束",
    "counter_consensus": "反共识视角",
}

AUDIENCE_ANGLE_CN = {
    "practical_application": "应用启发",
    "cognitive_update": "认知更新",
    "role_or_workflow_change": "角色/流程变化",
    "efficiency_or_quality": "效率/质量",
    "cost_or_resource": "成本/资源",
    "structural_impact": "结构性影响",
    "strategic_choice": "战略选择",
}


def reader_angle_cn(key: str, labels: dict[str, str] | None = None) -> str:
    labels = labels or READER_ANGLE_CN
    return labels.get(key, key)


def audience_angle_cn(key: str, labels: dict[str, str] | None = None) -> str:
    labels = labels or AUDIENCE_ANGLE_CN
    return labels.get(key, key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reader-dir", required=True, type=Path)
    parser.add_argument("--audience-dir", type=Path, help="可选；缺失视为仅 Reader 模式")
    parser.add_argument("--scored", required=True, type=Path, help="scored.json，用于过滤 tier 并排序")
    parser.add_argument("--output", required=True, type=Path, help="value_mapped.json")
    parser.add_argument("--angle-config", type=Path, default=Path("./references/angle_config.json"),
                        help="Reader/Audience angle key 与中文 label 配置")
    parser.add_argument("--dedup-threshold", type=float, default=0.72,
                        help="Jaccard 相似度阈值；>= 该值视为重复并 drop audience 块（默认 0.72）")
    args = parser.parse_args()
    reader_angle_keys, audience_angle_keys, reader_angle_labels, audience_angle_labels = load_angle_config(args.angle_config)

    scored = load_json(args.scored) or {"entries": []}
    # 过滤 tier，保留 must_read / recommended / optional；按 final_score 降序
    valid_entries = [e for e in scored.get("entries", []) if e.get("tier") in {"must_read", "recommended", "optional"}]
    valid_entries.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)

    entries: list[dict[str, Any]] = []
    global_warnings: list[dict[str, Any]] = []
    success = 0
    failure = 0

    for s in valid_entries:
        cid = s.get("cluster_id")
        if not cid:
            continue
        rp = args.reader_dir / f"{cid}.json"
        ap = (args.audience_dir / f"{cid}.json") if args.audience_dir else None
        reader_vm = load_json(rp)
        audience_vm = load_json(ap) if ap else None
        if not reader_vm:
            failure += 1
            global_warnings.append({"type": "missing_reader_vm", "cluster_id": cid, "message": f"{rp} 不存在"})
            continue
        if args.audience_dir and not audience_vm:
            global_warnings.append({"type": "missing_audience_vm", "cluster_id": cid, "message": f"{ap} 不存在（视为 Audience 视角全跳过）"})
        merged = merge_single(
            reader_vm,
            audience_vm,
            cid,
            args.dedup_threshold,
            reader_angle_keys,
            audience_angle_keys,
            reader_angle_labels,
            audience_angle_labels,
        )
        entries.append(merged)
        success += 1

    out = {
        "meta": {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "cluster_count": len(valid_entries),
            "success_count": success,
            "failure_count": failure,
            "dedup_threshold": args.dedup_threshold,
            "audience_enabled": bool(args.audience_dir),
        },
        "entries": entries,
        "warnings": global_warnings,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.output} · entries={success} · failure={failure} · audience_enabled={bool(args.audience_dir)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
