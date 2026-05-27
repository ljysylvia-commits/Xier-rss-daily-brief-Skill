#!/usr/bin/env python3
"""
Daily-Brief · Healthcheck
检查 Python 依赖 · 必要文件 · sources.md URL 可达性 · tmp/目录可写
由 SKILL.md Onboarding 段调用
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

REQUIRED_FILES = [
    ".gitignore",
    "LICENSE",
    "config/report_config.json",
    "references/PROFILE.md",
    "references/run_modes.md",
    "references/profile_onboarding.md",
    "references/sources.md",
    "references/source_recommendation.md",
    "references/feedback_loop.md",
    "references/prompt_hygiene.md",
    "references/scoring_profile.json",
    "references/scorer_input_contract.md",
    "references/agents/other-signal-summarizer.md",
    "references/angle_config.json",
    "references/EXAMPLE.md",
    "assets/daily.md.j2",
    "assets/daily.html.j2",
    "tests",
    "tests/role-reader-only",
    "tests/role-audience",
    "tests/marketing-lead-complex",
    "tests/final-others-quality",
    "tests/no-evidence-guardrail",
    "tests/rss-summary-not-demoted",
    "tests/other-signal-lint",
    "tests/warning-mapping",
    "tests/unsupported-source-boundary",
    "outputs/open-source-tests",
]
REQUIRED_SCRIPTS = [
    "scripts/fetch.py",
    "scripts/dedupe.py",
    "scripts/render.py",
    "scripts/merge_perspectives.py",
    "scripts/cleanup_tmp.py",
    "scripts/apply_scoring_guardrails.py",
    "scripts/build_other_signal_inputs.py",
    "scripts/run_contract_tests.py",
]
REQUIRED_PKGS = ["feedparser", "readability", "httpx", "simhash", "jinja2", "dateutil", "bs4"]

SOURCE_BLOCK_RE = re.compile(r"^\s*[-*]\s*(\{[^}]+\})\s*$", re.MULTILINE)
SOURCE_NAME_RE = re.compile(r"^###\s+\d+\.\s+(.+?)\s*$")
SOURCE_URL_RE = re.compile(r"^-\s+`url_primary`:\s+`([^`]+)`\s*$")
SOURCE_METHOD_RE = re.compile(r"^-\s+`fetch_method`:\s+`([^`]+)`\s*$")


def check_packages() -> list[tuple[str, bool, str]]:
    out = []
    for pkg in REQUIRED_PKGS:
        try:
            importlib.import_module(pkg)
            out.append((pkg, True, "ok"))
        except ImportError as e:
            out.append((pkg, False, str(e)))
    return out


def check_files(root: Path) -> list[tuple[str, bool, str]]:
    out = []
    for rel in REQUIRED_FILES + REQUIRED_SCRIPTS:
        p = root / rel
        out.append((rel, p.exists(), "ok" if p.exists() else "missing"))
    return out


def check_other_signal_prompt(root: Path) -> list[tuple[str, bool, str]]:
    path = root / "references" / "agents" / "other-signal-summarizer.md"
    if not path.exists():
        return [("other-signal-summarizer.x_mode_absent", False, "missing")]
    text = path.read_text(encoding="utf-8")
    forbidden = ["X Social 模式", "x_social_posts", "x_social_translated", "--x-social"]
    hits = [item for item in forbidden if item in text]
    return [("other-signal-summarizer.x_mode_absent", not hits, ",".join(hits) if hits else "ok")]


def check_no_personal_x_artifacts(root: Path) -> list[tuple[str, bool, str]]:
    forbidden_paths = [
        "scripts/split_social_posts.py",
        "x_social_posts.jsonl",
        "x_social_translated.json",
    ]
    path_hits = [rel for rel in forbidden_paths if (root / rel).exists()]

    forbidden_text = [
        "AI HOT",
        "aihot",
        "virxact",
        "x_social_posts",
        "x_social_translated",
        "--x-social",
        "split_social_posts.py",
        "X Social 模式",
        "Social Splitter",
    ]
    skip = {
        Path("scripts/healthcheck.py"),
        Path("scripts/run_contract_tests.py"),
    }
    text_hits: list[str] = []
    for base in ["README.md", "SKILL.md", "assets", "config", "references", "scripts"]:
        path = root / base
        paths = [path] if path.is_file() else list(path.rglob("*")) if path.exists() else []
        for candidate in paths:
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(root)
            if rel in skip or candidate.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".zip"}:
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for token in forbidden_text:
                if token in text:
                    text_hits.append(f"{rel}:{token}")
    hits = path_hits + text_hits
    return [("personal_x_artifacts_absent", not hits, "; ".join(hits) if hits else "ok")]


def check_report_config(root: Path) -> list[tuple[str, bool, str]]:
    path = root / "config" / "report_config.json"
    checks: list[tuple[str, bool, str]] = []
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [("config/report_config.json", False, f"invalid json: {e}")]

    formats = ((cfg.get("outputs") or {}).get("formats") or [])
    allowed_formats = {"markdown", "html"}
    formats_ok = isinstance(formats, list) and bool(formats) and set(formats).issubset(allowed_formats)
    checks.append(("outputs.formats", formats_ok, ",".join(formats) if formats_ok else "must be markdown/html list"))

    theme = cfg.get("html_theme")
    choices = set(cfg.get("html_theme_choices") or ["light", "dark"])
    checks.append(("html_theme", theme in choices, str(theme)))
    checks.append(("html_theme_choices", choices == {"light", "dark"}, ",".join(sorted(choices))))

    report_length = cfg.get("report_length") or {}
    length_ok = (
        report_length.get("max_must_read") == 3
        and report_length.get("max_recommended") == 5
        and report_length.get("max_optional") == 10
    )
    checks.append(("report_length", length_ok, json.dumps(report_length, ensure_ascii=False)))

    lifecycle_mode = (cfg.get("lifecycle") or {}).get("mode")
    lifecycle_ok = lifecycle_mode in {"demo", "setup", "tuning", "stable"}
    checks.append(("lifecycle.mode", lifecycle_ok, str(lifecycle_mode)))

    feedback_status = (cfg.get("feedback") or {}).get("status")
    feedback_ok = feedback_status in {"demo", "setup", "tuning", "stable"}
    checks.append(("feedback.status", feedback_ok, str(feedback_status)))

    automation = cfg.get("automation") or {}
    automation_enabled = bool(automation.get("enabled"))
    stable_gate_ok = (not automation_enabled) or feedback_status == "stable"
    checks.append(("automation.stable_gate", stable_gate_ok, "ok" if stable_gate_ok else "automation enabled before feedback stable"))

    stable_steps = (cfg.get("lifecycle") or {}).get("stable_daily_steps") or []
    expected = ["0", "1", "2", "3", "4", "4d", "5", "6"]
    checks.append(("lifecycle.stable_daily_steps", stable_steps == expected, ",".join(stable_steps)))
    return checks


def unsupported_url_type(url: str | None) -> str | None:
    if not url:
        return None
    host = httpx.URL(url).host or ""
    host = host.lower()
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}:
        return "x_twitter"
    if host.endswith(".twitter.com") or host.endswith(".x.com"):
        return "x_twitter"
    if host.startswith("nitter.") or ".nitter." in host:
        return "x_twitter"
    return None


def parse_source_urls(sources_md: Path) -> list[tuple[str, str, str]]:
    urls: list[tuple[str, str, str]] = []
    text = sources_md.read_text(encoding="utf-8")
    current_name = "source"
    pending_url: str | None = None
    pending_method = "rss"
    for line in text.splitlines():
        if m := SOURCE_NAME_RE.match(line):
            if pending_url:
                urls.append((current_name, pending_url, pending_method))
            current_name = m.group(1).strip()
            pending_url = None
            pending_method = "rss"
        elif m := SOURCE_URL_RE.match(line):
            pending_url = m.group(1).strip()
        elif m := SOURCE_METHOD_RE.match(line):
            pending_method = m.group(1).strip()
    if pending_url:
        urls.append((current_name, pending_url, pending_method))
    for m in SOURCE_BLOCK_RE.finditer(text):
        try:
            data = json.loads(m.group(1))
            if "id" in data and "url" in data:
                urls.append((data["id"], data["url"], data.get("fetch_method", "rss")))
        except json.JSONDecodeError:
            continue
    return urls


def source_quality(method: str, content: str) -> str:
    sample = content[:200_000].lower()
    if method == "rss":
        if "<rss" in sample or "<feed" in sample or sample.count("<item") + sample.count("<entry") >= 2:
            return "rss_like"
        return "reachable_but_not_rss_like"
    if method in {"archive_scrape", "hybrid"}:
        links = sample.count("href=")
        titles = sample.count("<article") + sample.count("<h1") + sample.count("<h2") + sample.count("<h3")
        if links >= 5 and titles >= 1:
            return "archive_like"
        return "reachable_but_low_archive_signal"
    return "reachable"


def probe(client: httpx.Client, sid: str, url: str, method: str) -> tuple[str, str, int | None, str, str]:
    unsupported = unsupported_url_type(url)
    if unsupported:
        return sid, url, None, "unsupported", f"unsupported_source_type:{unsupported}"
    try:
        r = client.head(url, follow_redirects=True, timeout=10.0)
        if r.status_code >= 400 or r.status_code == 405:
            r = client.get(url, follow_redirects=True, timeout=10.0)
        quality = "not_checked"
        if r.status_code < 400:
            if not r.text:
                r = client.get(url, follow_redirects=True, timeout=10.0)
            quality = source_quality(method, r.text or "")
        return sid, url, r.status_code, "ok" if r.status_code < 400 else "dead", quality
    except Exception as e:
        return sid, url, None, f"error:{e.__class__.__name__}", "not_checked"


def check_tmp(root: Path) -> tuple[bool, str]:
    tmp = root / "tmp"
    try:
        tmp.mkdir(exist_ok=True)
        probe_file = tmp / ".healthcheck_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        return True, "writable"
    except Exception as e:
        return False, str(e)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--probe-sources", action="store_true", help="HEAD-check sources.md URLs")
    args = parser.parse_args()

    root = args.root
    failed = 0

    print("=== Python packages ===")
    for name, ok, msg in check_packages():
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:14s} {msg}")
        if not ok:
            failed += 1

    print("\n=== Required files ===")
    for rel, ok, msg in check_files(root):
        mark = "✅" if ok else "❌"
        print(f"  {mark} {rel:40s} {msg}")
        if not ok:
            failed += 1

    print("\n=== Report config ===")
    for name, ok, msg in check_report_config(root):
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:32s} {msg}")
        if not ok:
            failed += 1

    print("\n=== Prompt contracts ===")
    for name, ok, msg in check_other_signal_prompt(root) + check_no_personal_x_artifacts(root):
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name:40s} {msg}")
        if not ok:
            failed += 1

    print("\n=== tmp/ writable ===")
    ok, msg = check_tmp(root)
    print(f"  {'✅' if ok else '❌'} tmp/ → {msg}")
    if not ok:
        failed += 1

    if args.probe_sources:
        print("\n=== sources.md URL probe ===")
        srcs = parse_source_urls(root / "references" / "sources.md")
        if not srcs:
            print("  ⚠️ no sources parsed")
        with httpx.Client(headers={"User-Agent": "daily-brief-healthcheck"}) as client:
            with ThreadPoolExecutor(max_workers=10) as pool:
                futs = [pool.submit(probe, client, sid, url, method) for sid, url, method in srcs]
                for fut in as_completed(futs):
                    sid, url, code, status, quality = fut.result()
                    mark = "✅" if status == "ok" and not quality.startswith("reachable_but") else "⚠️"
                    print(f"  {mark} {sid:28s} {code} {status} · {quality}")

    print(f"\nfailed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
