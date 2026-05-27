#!/usr/bin/env python3
"""
Daily-Brief · Writer
规范见 agents/writer.md · EXAMPLE.md
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

INTERNAL_CLUSTER_RE = re.compile(r"\bc\d{4,}\b", re.IGNORECASE)


def clean_user_text(text: str) -> str:
    """Remove internal runtime ids from user-facing text."""
    if not text:
        return ""
    text = INTERNAL_CLUSTER_RE.sub("对应主条目", text)
    return text.replace("${RUN_DIR}", "中间产物目录")

PILLAR_LABEL = {
    "pillar_1_signal_decode": "信号解读",
    "pillar_2_practice": "实践拆解",
    "pillar_3_methodology": "方法论",
    "pillar_4_exploration": "思考与探索",
}

# 默认 angle label；运行时优先读取 references/angle_config.json。
READER_ANGLE_LABEL = {
    "decision_impact": "决策影响",
    "context_shift": "背景变化",
    "cognitive_framework": "认知框架",
    "workflow_action": "行动方法",
    "system_or_product_signal": "系统/产品信号",
    "firsthand_evidence": "一手证据",
    "risk_or_constraint": "风险与约束",
    "counter_consensus": "反共识视角",
}

DEFAULT_REPORT_CONFIG = {
    "locale": "zh-CN",
    "output_language": "zh",
    "report_title": "今日简报",
    "report_subtitle": "Configurable Public-Source Daily Brief",
    "html_theme": "light",
    "html_theme_choices": ["light", "dark"],
    "outputs": {
        "formats": ["markdown", "html"],
        "directory": "outputs/daily-brief",
    },
    "outlook": {
        "style": "strategic_synthesis",
        "min_items": 2,
        "max_items": 5,
        "include_content_pillars": False,
    },
    "report_length": {
        "max_must_read": 3,
        "max_recommended": 5,
        "max_optional": 10,
        "show_other_table": True,
    },
    "labels": {
        "outlook": "今日格局",
        "reader_value": "💡 对读者的价值",
        "audience_value": "🎯 对目标受众的价值",
        "pillars": "📚 内容支柱归位",
        "source_metadata": "重点信息",
        "core_content": "核心内容",
        "reading_suggestion": "阅读建议",
        "other_sources": "其他来源",
        "source_health": "信源状态",
    },
    "features": {
        "audience_view": True,
        "pillar_mapping": False,
        "translate_others_to_output_language": True,
    },
    "html": {
        "max_width_px": 720,
        "show_terminal_bar": True,
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_report_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return DEFAULT_REPORT_CONFIG
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return DEFAULT_REPORT_CONFIG
    return deep_merge(DEFAULT_REPORT_CONFIG, data if isinstance(data, dict) else {})


def normalize_output_formats(report_config: dict[str, Any], override: str | None) -> list[str]:
    raw = override
    if raw is None:
        outputs = report_config.get("outputs") or {}
        raw = outputs.get("formats", ["markdown", "html"])
    if isinstance(raw, str):
        values = [x.strip().lower() for x in raw.split(",") if x.strip()]
    elif isinstance(raw, list):
        values = [str(x).strip().lower() for x in raw if str(x).strip()]
    else:
        values = ["markdown", "html"]
    aliases = {"md": "markdown", "html": "html", "markdown": "markdown"}
    formats: list[str] = []
    for value in values:
        fmt = aliases.get(value)
        if fmt and fmt not in formats:
            formats.append(fmt)
    return formats or ["markdown", "html"]


def configured_output_path(
    explicit: Path | None,
    report_config: dict[str, Any],
    run_date: str,
    suffix: str,
) -> Path:
    if explicit:
        return explicit
    outputs = report_config.get("outputs") or {}
    out_dir = Path(outputs.get("directory") or "outputs/daily-brief")
    return out_dir / f"{run_date}.{suffix}"

AUDIENCE_ANGLE_LABEL = {
    "practical_application": "应用启发",
    "cognitive_update": "认知更新",
    "role_or_workflow_change": "角色/流程变化",
    "efficiency_or_quality": "效率/质量",
    "cost_or_resource": "成本/资源",
    "structural_impact": "结构性影响",
    "strategic_choice": "战略选择",
}


def load_angle_labels(path: Path | None) -> tuple[dict[str, str], dict[str, str]]:
    """读取 angle_config.json；缺失时回退到内置默认 label。"""
    if path is None or not path.exists():
        return dict(READER_ANGLE_LABEL), dict(AUDIENCE_ANGLE_LABEL)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return dict(READER_ANGLE_LABEL), dict(AUDIENCE_ANGLE_LABEL)

    def labels_for(section: str, fallback: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in data.get(section, []) or []:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if key:
                out[str(key)] = str(item.get("label_zh") or key)
        return out or dict(fallback)

    return labels_for("reader", READER_ANGLE_LABEL), labels_for("audience", AUDIENCE_ANGLE_LABEL)


def _load_pillar_config(path: Path | None) -> dict[str, str]:
    """读 pillar_config.json；缺失则回退到模块级 PILLAR_LABEL。

    结构约定（SSOT）：pillars 为 list[{key, name_zh, ...}]。
    """
    if path is None or not path.exists():
        return PILLAR_LABEL
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return PILLAR_LABEL
    out: dict[str, str] = {}
    for p in (data.get("pillars") or []):
        if isinstance(p, dict):
            k = p.get("key")
            name = p.get("name_zh")
            if k and name:
                out[k] = name
    return out or PILLAR_LABEL


TIER_ORDER = ["must_read", "recommended", "optional", "others"]


def load_json(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


GENERIC_GIST_PHRASES = [
    "这是一条来自",
    "主题为",
]
MAX_GIST_CHARS = 80


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def has_long_english_fragment(text: str) -> bool:
    return bool(re.search(r"[A-Za-z][A-Za-z0-9 ,.;:!?()/'\"+\-]{48,}", text or ""))


def normalize_for_overlap(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def text_units(text: str) -> set[str]:
    normalized = normalize_for_overlap(text)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    cjk = [a + b for a, b in zip(cjk_chars, cjk_chars[1:])]
    words = re.findall(r"[a-z0-9]+", normalized)
    return set(cjk + words)


def title_gist_similarity(title: str, gist: str) -> float:
    title_units = text_units(title)
    gist_units = text_units(gist)
    if not title_units or not gist_units:
        return 0.0
    return len(title_units & gist_units) / len(title_units)


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def validate_translation_entry(entry: dict[str, Any], *, label: str) -> None:
    cid = entry.get("cluster_id")
    title = (entry.get("title_zh") or "").strip()
    gist = (entry.get("gist_zh") or "").strip()
    if not cid:
        raise ValueError(f"{label}: missing cluster_id")
    if not title:
        raise ValueError(f"{label}: {cid} missing title_zh")
    if not gist:
        raise ValueError(f"{label}: {cid} missing gist_zh")
    if gist != "中文摘要缺失" and compact_len(gist) > MAX_GIST_CHARS:
        raise ValueError(f"{label}: {cid} gist_zh exceeds {MAX_GIST_CHARS} chars")
    if not has_cjk(gist):
        raise ValueError(f"{label}: {cid} gist_zh must contain Chinese")
    if has_long_english_fragment(gist):
        raise ValueError(f"{label}: {cid} gist_zh contains long English fragment")
    if any(p in gist for p in GENERIC_GIST_PHRASES):
        raise ValueError(f"{label}: {cid} gist_zh uses generic template phrasing")
    if normalize_for_overlap(title) == normalize_for_overlap(gist):
        raise ValueError(f"{label}: {cid} gist_zh duplicates title_zh")
    if title_gist_similarity(title, gist) >= 0.82:
        raise ValueError(f"{label}: {cid} gist_zh is too similar to title_zh")


def load_translation_json(path: Path | None, *, arg_name: str, required: bool) -> dict[str, Any]:
    if path is None:
        if required:
            raise ValueError(f"{arg_name} is required")
        return {"entries": []}
    if not path.exists():
        raise ValueError(f"{arg_name} was provided but the file does not exist")
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{arg_name} must be a JSON object")
    if set(data.keys()) != {"entries"}:
        raise ValueError(f"{arg_name} must use only root key entries")
    if not isinstance(data.get("entries"), list):
        raise ValueError(f"{arg_name} must contain entries[]")
    return data


def evidence_unavailable(cluster: dict[str, Any] | None) -> bool:
    if not cluster:
        return False
    try:
        primary_tokens = int(cluster.get("primary_tokens") or 0)
    except (TypeError, ValueError):
        primary_tokens = 0
    rss_summary = cluster.get("rss_summary")
    return (
        primary_tokens == 0
        and not str(rss_summary or "").strip()
        and cluster.get("fetch_status") == "content_extraction_failed"
    )


def validate_others_translated(
    others_tr: dict[str, Any],
    required_ids: list[str],
    clusters_index: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    cluster_by_id = {
        c.get("cluster_id"): c
        for c in clusters_index.get("clusters", [])
        if isinstance(c, dict) and c.get("cluster_id")
    }
    by_id: dict[str, dict[str, Any]] = {}
    for entry in others_tr.get("entries", []):
        if not isinstance(entry, dict):
            raise ValueError("--others-translated entries[] must contain objects")
        validate_translation_entry(entry, label="--others-translated")
        cid = entry["cluster_id"]
        if cid in by_id:
            raise ValueError(f"--others-translated duplicate cluster_id: {cid}")
        by_id[cid] = entry
    missing = [cid for cid in required_ids if cid not in by_id]
    if missing:
        raise ValueError("--others-translated missing cluster_id: " + ", ".join(missing))
    unexpected = [cid for cid in by_id if cid not in set(required_ids)]
    if unexpected:
        raise ValueError("--others-translated unexpected cluster_id: " + ", ".join(unexpected))
    for cid in required_ids:
        gist = (by_id[cid].get("gist_zh") or "").strip()
        if evidence_unavailable(cluster_by_id.get(cid)):
            if gist != "中文摘要缺失":
                raise ValueError(
                    f"--others-translated: {cid} evidence unavailable, gist_zh must be 中文摘要缺失"
                )
        elif gist == "中文摘要缺失":
            raise ValueError(f"--others-translated: {cid} gist_zh cannot be 中文摘要缺失 when evidence is available")
    return by_id


def build_badges(row: dict[str, Any]) -> list[str]:
    badges: list[str] = []
    tier = row.get("tier")
    if tier == "must_read":
        badges.append("🔥 必读")
    elif tier == "recommended":
        badges.append("⭐ 推荐")
    elif tier == "optional":
        badges.append("📌 可选")
    if row.get("non_consensus_flag"):
        badges.append("💥 非共识")
    if row.get("is_followup"):
        badges.append("📎 续报")
    if row.get("match_mode") == "ai_discovered":
        badges.append("🔍 AI 推荐")
    if (row.get("spam_confidence") or 0) >= 0.6:
        badges.append("⚠️ 疑似水文")
    return badges


def render_pillars(pillars: list[str] | None, pillar_label: dict[str, str]) -> str:
    if not pillars:
        return "无（市场动态感知）"
    return " · ".join(pillar_label.get(p, p) for p in pillars)


def pillar_mapping_enabled(report_config: dict[str, Any]) -> bool:
    features = report_config.get("features") or {}
    return bool(features.get("pillar_mapping", False))


def outlook_pillars_enabled(report_config: dict[str, Any]) -> bool:
    outlook_cfg = report_config.get("outlook") or {}
    return pillar_mapping_enabled(report_config) and bool(outlook_cfg.get("include_content_pillars", False))


def filter_outlook_items(items: list[dict[str, Any]], include_pillars: bool) -> list[dict[str, Any]]:
    if include_pillars:
        return items
    out: list[dict[str, Any]] = []
    for item in items:
        tag = str(item.get("tag") or "")
        if item.get("modules") or "内容支柱" in tag or "Content Pillar" in tag:
            continue
        out.append(item)
    return out


def split_value_blocks(vm: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """v0.10：按 perspective 分 reader / audience 两组，供 daily.md.j2 分段渲染。"""
    if not vm:
        return [], []
    blocks = vm.get("value_blocks") or []
    reader = [b for b in blocks if b.get("perspective") == "reader"]
    audience = [b for b in blocks if b.get("perspective") == "audience"]
    return reader, audience


def merge_row(
    cluster_meta: dict[str, Any],
    scored: dict[str, Any],
    vm: dict[str, Any] | None,
    pillar_label: dict[str, str],
) -> dict[str, Any]:
    row = {**scored, **cluster_meta}
    # template 语义字段别名：clusters_index 实际字段名 "title" / "language" / "primary_tokens"
    # template 里继续用 primary_* 命名以便和 VM 产物 title_zh 等区分
    if cluster_meta.get("title") and not row.get("primary_title"):
        row["primary_title"] = cluster_meta["title"]
    if cluster_meta.get("language") and not row.get("primary_lang"):
        row["primary_lang"] = cluster_meta["language"]
    row["value_mapped"] = vm or {}
    row["badges"] = build_badges(scored)
    row["pillars_display"] = render_pillars((vm or {}).get("pillars"), pillar_label)
    row["degraded"] = bool((vm or {}).get("degraded"))
    row["warnings_short"] = summarize_warnings((vm or {}).get("warnings") or [])
    if (vm or {}).get("reading_suggestion"):
        vm = {**(vm or {}), "reading_suggestion": clean_user_text((vm or {}).get("reading_suggestion") or "")}
        row["value_mapped"] = vm
    # v0.10：按 perspective 切分 value_blocks
    reader_blocks, audience_blocks = split_value_blocks(vm)
    row["reader_blocks"] = reader_blocks
    row["audience_blocks"] = audience_blocks
    return row


WARNING_SHORT_LABEL = {
    "too_sparse": "内容深度受限（细节可能遗漏）",
    "sparse_content": "内容深度受限",
    "content_depth_limited": "内容深度受限",
    "fetch_failed": "抓取异常",
    "stale_content": "非窗口新增",
    "freshness_stale": "非窗口新增",
    "title_content_mismatch": "RSS 源标题/正文主题不符",
    "scoring_note": "质量校正说明",
    "freshness": "时效性告警",
    "lint_fail": "部分价值块未通过质量校验，已自动剔除",
    "missing_reader_vm": "读者视角生成失败",
    "missing_audience_vm": "企业视角生成失败",
    "source_uncertainty": "信源需核验",
    "source_unverified": "信源需核验",
    "unconfirmed_rumor": "未官宣信息，需核验",
}

AUTO_DEMOTED_REASON_LABEL = {
    "title_content_mismatch": "RSS 源标题/正文主题不符",
}

TIER_LABEL = {
    "must_read": "必读",
    "recommended": "推荐",
    "optional": "可选",
    "others": "其他",
}


def summarize_warnings(warnings: list[Any]) -> str:
    """Value-Mapper warnings 结构化精简：每条一句话，去掉 JSON dump。"""
    if not warnings:
        return ""
    parts: list[str] = []
    for w in warnings:
        if isinstance(w, dict):
            wtype = w.get("type", "unknown")
        else:
            wtype = str(w)
        key = "duplicate_event_of" if wtype.startswith("duplicate_event_of") else wtype
        label = WARNING_SHORT_LABEL.get(key, "需人工复核")
        if wtype.startswith("duplicate_event_of"):
            label = "跨源同事件（Deduper 漏合并）"
        parts.append(label)
    # 去重保序
    seen: set[str] = set()
    uniq = []
    for p in parts:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    return " · ".join(uniq)


def has_mismatch_warning(vm: dict[str, Any] | None) -> bool:
    """C1：检测 title_content_mismatch warning，用于自动降级到 others tier"""
    for w in (vm or {}).get("warnings", []):
        wtype = w.get("type") if isinstance(w, dict) else str(w)
        if wtype == "title_content_mismatch":
            return True
    return False


def attach_primary_gist(rows: list[dict[str, Any]], raw_items_path: Path) -> None:
    """
    从 raw_items.jsonl 拉每个 cluster.primary 的原文前 100 字，挂到 row.primary_gist。
    仅供 debug/QA 检查；正式模板不再把 raw gist 作为 Other Signals fallback。
    """
    if not raw_items_path.exists():
        return
    # 构建 (source_name, url) -> full_content first 200 chars 的索引
    by_url: dict[str, str] = {}
    with raw_items_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            it = json.loads(line)
            url = (it.get("source_url") or "").strip()
            if url:
                content = (it.get("full_content") or "").strip()
                by_url[url] = content
    for r in rows:
        url = r.get("primary_url")
        if not url:
            continue
        content = by_url.get(url, "")
        if content:
            # 取前 120 字（template 再 truncate 100）
            r["primary_gist"] = content[:240].replace("\n", " ").strip()


def group_by_tier(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[r.get("tier", "others")].append(r)
    for key in buckets:
        buckets[key].sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    return buckets


def rebalance_tiers(rows: list[dict[str, Any]], report_config: dict[str, Any]) -> list[dict[str, Any]]:
    """按日报长度配置重分展示层 tier；只下放超额条目，不把 others 往上提。"""
    length_cfg = report_config.get("report_length") or {}
    caps = {
        "must_read": max(int(length_cfg.get("max_must_read", 3)), 0),
        "recommended": max(int(length_cfg.get("max_recommended", 5)), 0),
        "optional": max(int(length_cfg.get("max_optional", 10)), 0),
    }
    eligible: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for row in rows:
        original_tier = row.get("original_tier") or row.get("tier")
        item = {**row, "original_tier": original_tier}
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
                new_item["original_tier_label"] = TIER_LABEL.get(new_item.get("original_tier"), new_item.get("original_tier"))
            new_item["badges"] = build_badges({**new_item, "tier": tier})
            out.append(new_item)
        cursor += caps[tier]

    for item in eligible[cursor:]:
        new_item = {**item, "tier": "others", "tier_adjusted_reason": "report_length_cap"}
        new_item["original_tier_label"] = TIER_LABEL.get(new_item.get("original_tier"), new_item.get("original_tier"))
        new_item["badges"] = build_badges({**new_item, "tier": "others"})
        others.append(new_item)

    return out + others


def source_health_sections(fetcher_log: Path | None) -> dict[str, list[str]]:
    """极简解析 fetcher.log 的 freshness summary 行。

    v0.10.2：新增 `no_new_items` 第五档（sources.md 注册但本次 0 新内容的源）。
    与 stale/irregular/dead 不同 —— no_new_items 代表 "通道健康 · 今日无新内容"，
    不是健康度告警。`unsupported` 代表当前开源版不支持的 source URL 类型。
    """
    sections = {
        "fresh": [],
        "no_new_items": [],
        "stale": [],
        "irregular": [],
        "dead": [],
        "unsupported": [],
    }
    if fetcher_log is None or not fetcher_log.exists():
        return sections
    # v0.10.2：只取最后一条 freshness summary，避免 log 若被 append 模式写入时双计数
    last_payload: dict[str, str] | None = None
    for line in fetcher_log.read_text(encoding="utf-8").splitlines():
        if "freshness summary" in line:
            try:
                payload = line.split("freshness summary:", 1)[1].strip()
                last_payload = json.loads(payload)
            except (ValueError, json.JSONDecodeError):
                continue
    if last_payload:
        for src, state in last_payload.items():
            sections.setdefault(state, []).append(src)
    return sections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clusters-index", required=True, type=Path)
    parser.add_argument("--scored", required=True, type=Path)
    parser.add_argument("--value-mapped", required=True, type=Path)
    parser.add_argument("--others-translated", required=True, type=Path, help="others_translated.json，others 的中文 title/gist")
    parser.add_argument("--outlook", type=Path)
    parser.add_argument("--fetcher-log", type=Path, default=Path("./tmp/fetcher.log"),
                        help="fetcher.log 路径，用于解析 freshness summary 填充信源状态。"
                             "v0.10.2：默认 ./tmp/fetcher.log，存在即用，不存在静默降级为空健康度。")
    parser.add_argument("--raw-items", type=Path, help="raw_items.jsonl，仅用于 QA/debug 挂载 primary_gist")
    parser.add_argument("--run-context", type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--html-template", type=Path, help="可选：HTML Jinja2 模板")
    parser.add_argument("--html-output", type=Path, help="可选：HTML 输出路径")
    parser.add_argument("--output-formats",
                        help="可选：覆盖 report_config.outputs.formats。支持 markdown,html / markdown / html")
    parser.add_argument("--report-config", type=Path, default=Path("./config/report_config.json"),
                        help="可选：日报标题、输出语言、section label、HTML theme 配置")
    parser.add_argument("--html-theme", choices=["light", "dark"],
                        help="可选：覆盖 report_config.json 中的 html_theme")
    parser.add_argument("--angle-config", type=Path, default=Path("./references/angle_config.json"),
                        help="Reader/Audience angle key 与中文 label 配置")
    parser.add_argument("--pillar-config", type=Path, default=Path("./references/pillar_config.json"),
                        help="可选：references/pillar_config.json。仅在 features.pillar_mapping=true 时用于渲染内容支柱标签")
    args = parser.parse_args()

    pillar_label = _load_pillar_config(args.pillar_config)
    report_config = load_report_config(args.report_config)
    reader_angle_label, audience_angle_label = load_angle_labels(args.angle_config)
    if args.html_theme:
        report_config["html_theme"] = args.html_theme
    pillars_enabled = pillar_mapping_enabled(report_config)
    outlook_modules_enabled = outlook_pillars_enabled(report_config)
    output_formats = normalize_output_formats(report_config, args.output_formats)
    if "html" in output_formats and not args.html_template:
        parser.error("--html-template is required when output format includes html")

    clusters_index = load_json(args.clusters_index) or {"clusters": []}
    scored = load_json(args.scored) or {"entries": []}
    value_mapped = load_json(args.value_mapped) or {"entries": []}
    outlook = load_json(args.outlook) or {"daily_outlook": []}
    daily_outlook = filter_outlook_items(outlook.get("daily_outlook", []), outlook_modules_enabled)
    # 预渲染 outlook 每条为 markdown 字符串（支持 structured modules 缩进）
    for _o in daily_outlook:
        _tag = _o.get("tag", "观察")
        _mods = _o.get("modules") or []
        if _mods:
            _lines = [f"- **{_tag}**"]
            for _m in _mods:
                if (_m.get("count") or 0) > 0 and (_m.get("items") or []):
                    _lines.append(f"  - **{_m.get('name')}**（{_m.get('count')} 条）：{' / '.join(_m.get('items') or [])}")
            _o["_md"] = "\n".join(_lines)
        else:
            _o["_md"] = f"- **{_tag}** — {_o.get('body', '(空)')}"
    try:
        others_tr = load_translation_json(args.others_translated, arg_name="--others-translated", required=True)
    except ValueError as e:
        parser.error(str(e))
    run_ctx = load_json(args.run_context) or {}

    cluster_meta_by_id = {c["cluster_id"]: c for c in clusters_index.get("clusters", [])}
    # value-mapper §5：cluster_id 在 meta 里；顶层 cluster_id 是可选回退
    vm_by_id = {
        (v.get("meta") or {}).get("cluster_id") or v.get("cluster_id"): v
        for v in value_mapped.get("entries", [])
    }

    rows: list[dict[str, Any]] = []
    auto_demoted: list[str] = []
    for s in scored.get("entries", []):
        cid = s.get("cluster_id")
        cm = cluster_meta_by_id.get(cid)
        if not cm:
            continue
        vm = vm_by_id.get(cid)
        row = merge_row(cm, s, vm, pillar_label)
        # P1-J：标记是否来自 stale_penalty > 0（Scorer 判定的过窗内容）
        row["is_stale"] = (s.get("stale_penalty") or 0) > 0
        # C1：title_content_mismatch 自动降级 others
        if has_mismatch_warning(vm) and row.get("tier") != "others":
            row["original_tier"] = row.get("tier")
            row["original_tier_label"] = TIER_LABEL.get(row["original_tier"], row["original_tier"])
            row["tier"] = "others"
            row["auto_demoted_reason"] = "title_content_mismatch"
            row["auto_demoted_reason_label"] = AUTO_DEMOTED_REASON_LABEL.get(
                "title_content_mismatch", "title_content_mismatch"
            )
            # badges 重建（others 不要 tier 徽章）
            row["badges"] = build_badges({**s, "tier": "others"})
            auto_demoted.append(cid)
        rows.append(row)

    # 给 QA/debug 补 primary_gist；正式模板不再把 raw gist 作为用户可见 fallback。
    if args.raw_items:
        attach_primary_gist(rows, args.raw_items)

    rows = rebalance_tiers(rows, report_config)
    others_required_ids = [r.get("cluster_id") for r in rows if r.get("tier") == "others" and r.get("cluster_id")]
    try:
        others_tr_by_id = validate_others_translated(others_tr, others_required_ids, clusters_index)
    except ValueError as e:
        parser.error(str(e))

    # G2：把最终 Other Signals 的中文翻译挂到 row（title_zh_others / gist_zh_others）
    for r in rows:
        cid = r.get("cluster_id")
        tr = others_tr_by_id.get(cid)
        if tr:
            r["title_zh_others"] = tr.get("title_zh")
            r["gist_zh_others"] = tr.get("gist_zh")

    tier_buckets = group_by_tier(rows)
    tier_counts = {k: len(v) for k, v in tier_buckets.items()}

    # P1-J：others 分组排序 → (auto_demoted, 正常 fresh, 正常 stale)
    others_rows = tier_buckets.get("others", [])
    others_demoted = [r for r in others_rows if r.get("auto_demoted_reason")]
    others_natural = [r for r in others_rows if not r.get("auto_demoted_reason")]
    others_fresh = [r for r in others_natural if not r.get("is_stale")]
    others_stale = [r for r in others_natural if r.get("is_stale")]
    # 每组仍按 final_score 降序
    for grp in (others_demoted, others_fresh, others_stale):
        grp.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    others_ordered = others_demoted + others_fresh + others_stale
    others_subcounts = {
        "demoted": len(others_demoted),
        "fresh": len(others_fresh),
        "stale": len(others_stale),
    }

    special_counts = Counter()
    for r in rows:
        if r.get("match_mode") == "ai_discovered":
            special_counts["ai_discovered"] += 1
        if r.get("is_followup"):
            special_counts["followup"] += 1
        if r.get("non_consensus_flag"):
            special_counts["non_consensus"] += 1
        if (r.get("spam_confidence") or 0) >= 0.6:
            special_counts["spam"] += 1

    env = Environment(
        loader=FileSystemLoader(str(args.template.parent)),
        autoescape=select_autoescape(enabled_extensions=()),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    tpl = env.get_template(args.template.name)

    today = datetime.now().strftime("%Y-%m-%d")
    md_output = configured_output_path(args.output, report_config, today, "md")
    html_output = configured_output_path(args.html_output, report_config, today, "html")
    regenerated = md_output.exists() if "markdown" in output_formats else html_output.exists()

    ctx = {
        "date": today,
        "regenerated": regenerated,
        "now_str": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_clusters": clusters_index.get("count", len(clusters_index.get("clusters", []))),
        "tier_counts": tier_counts,
        "tier_order": TIER_ORDER,
        "special_counts": dict(special_counts),
        "must_read": tier_buckets.get("must_read", []),
        "recommended": tier_buckets.get("recommended", []),
        "optional": tier_buckets.get("optional", []),
        "others": others_ordered,
        "others_subcounts": others_subcounts,
        "others_demoted": others_demoted,
        "others_fresh": others_fresh,
        "others_stale": others_stale,
        "outlook": daily_outlook,
        "outlook_degraded": not daily_outlook,
        "source_health": source_health_sections(args.fetcher_log),
        "run_context": run_ctx,
        "pillar_label": pillar_label,
        "report_config": report_config,
        "labels": report_config.get("labels") or {},
        "pillars_enabled": pillars_enabled,
        "reader_angle_label": reader_angle_label,
        "audience_angle_label": audience_angle_label,
    }

    if "markdown" in output_formats:
        rendered = tpl.render(**ctx)
        md_output.parent.mkdir(parents=True, exist_ok=True)
        md_output.write_text(rendered, encoding="utf-8")
        print(f"wrote {md_output} size={md_output.stat().st_size}")
    else:
        print("skipped markdown output by config")
    if "html" in output_formats:
        html_env = Environment(
            loader=FileSystemLoader(str(args.html_template.parent)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        html_tpl = html_env.get_template(args.html_template.name)
        html_rendered = html_tpl.render(**ctx)
        html_output.parent.mkdir(parents=True, exist_ok=True)
        html_output.write_text(html_rendered, encoding="utf-8")
        print(f"wrote {html_output} size={html_output.stat().st_size}")
    else:
        print("skipped html output by config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
