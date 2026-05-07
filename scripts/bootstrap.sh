#!/usr/bin/env bash
# Daily-Brief Skill · bootstrap.sh
# 幂等：已装的包跳过；只补缺失的。
# 适配 PEP 668 管理环境，目标目录为用户本地 Python 环境。

set -e

# 运行时 import 名 vs. PyPI 包名（readability-lxml 的 import 名是 readability）。
# Keep this Bash 3 compatible for macOS default /bin/bash.
IMPORT_NAMES=(
  feedparser
  httpx
  h2
  lxml
  lxml_html_clean
  bs4
  dateutil
  simhash
  jinja2
  readability
)

PYPI_NAMES=(
  feedparser
  "httpx[http2]"
  h2
  lxml
  lxml_html_clean
  beautifulsoup4
  python-dateutil
  simhash
  jinja2
  readability-lxml
)

MISSING=()
for i in "${!IMPORT_NAMES[@]}"; do
  imp="${IMPORT_NAMES[$i]}"
  if ! python3 -c "import $imp" 2>/dev/null; then
    MISSING+=("${PYPI_NAMES[$i]}")
  fi
done

if [ ${#MISSING[@]} -eq 0 ]; then
  echo "[bootstrap] all 10 deps satisfied, skip"
  exit 0
fi

echo "[bootstrap] installing to ~/.local/: ${MISSING[*]}"
pip3 install --user --break-system-packages --quiet "${MISSING[@]}"

# 二次校验
FAIL=()
for imp in "${IMPORT_NAMES[@]}"; do
  python3 -c "import $imp" 2>/dev/null || FAIL+=("$imp")
done

if [ ${#FAIL[@]} -gt 0 ]; then
  echo "[bootstrap] FAIL: these still cannot import: ${FAIL[*]}" >&2
  exit 1
fi

echo "[bootstrap] done, all deps ready"
