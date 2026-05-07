# Demo 信源列表（sources.md）

> 用途：生产使用前替换本 demo 列表。fetcher 只支持公开 HTTP 信源。

## Schema

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 展示名称 |
| `url_primary` | URL | 主要抓取入口 |
| `url_fallback` | URL? | 可选 fallback 页面 |
| `fetch_method` | enum | `rss` / `archive_scrape` / `hybrid` |
| `freshness` | enum | `daily` / `weekly` / `monthly` / `irregular` |
| `depth` | enum | `full_text` / `rich_description` / `summary_only` |
| `lang` | enum | `en` / `zh` / `mixed` |
| `priority` | string? | 用户相关的评分提示 |
| `note` | string | 客观信源说明 |

所有信源使用同一个 coverage window。weekly source 在过去 24 小时没有新条目是正常情况。

## Demo 气候 / 公共政策信源

这些是中性的开源 demo sources，不代表任何用户的私人偏好。

### 1. Yale Climate Connections

- `url_primary`: `https://yaleclimateconnections.org/feed/`
- `url_fallback`: `https://yaleclimateconnections.org/`
- `fetch_method`: `rss`
- `freshness`: `daily`
- `depth`: `full_text`
- `lang`: `en`
- `priority`: `core_authority_climate_communication`
- `note`: 气候报道和公共沟通。

### 2. Carbon Brief

- `url_primary`: `https://www.carbonbrief.org/feed/`
- `url_fallback`: `https://www.carbonbrief.org/`
- `fetch_method`: `rss`
- `freshness`: `daily`
- `depth`: `full_text`
- `lang`: `en`
- `priority`: `evidence_and_policy_analysis`
- `note`: 气候科学、政策和证据解释。

### 3. FEMA Blog

- `url_primary`: `https://www.fema.gov/blog/rss.xml`
- `url_fallback`: `https://www.fema.gov/blog`
- `fetch_method`: `rss`
- `freshness`: `weekly`
- `depth`: `rich_description`
- `lang`: `en`
- `priority`: `public_agency_practice`
- `note`: 公共机构发布的应急管理和韧性实践。

### 4. Urban Institute

- `url_primary`: `https://www.urban.org/rss.xml`
- `url_fallback`: `https://www.urban.org/`
- `fetch_method`: `rss`
- `freshness`: `weekly`
- `depth`: `summary_only`
- `lang`: `en`
- `priority`: `urban_policy_research`
- `note`: 城市政策研究和公共项目语境。
