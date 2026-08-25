from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlencode


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "case-gallery" / "cases.json"
CSS_PATH = REPO_ROOT / "case-gallery" / "site.css"
PUBLIC_ROOT = "https://datou202307-design.github.io/trend-opportunity-radar"
REPOSITORY_URL = "https://github.com/datou202307-design/trend-opportunity-radar"
RELEASE_URL = f"{REPOSITORY_URL}/releases/latest"
DISCUSSIONS_URL = f"{REPOSITORY_URL}/discussions"
ALLOWED_MODES = {
    "business_opportunity",
    "brand_sentiment",
    "competitor_users",
    "content_opportunity",
    "product_demand",
}


UI = {
    "en": {
        "locale": "en",
        "title": "Trend Opportunity Radar Case Gallery",
        "description": "Five synthetic examples show how one evidence-backed Agent Skill supports business, brand, competitor, content, and product decisions.",
        "language": "简体中文",
        "brand": "Trend Opportunity Radar",
        "nav_cases": "Cases",
        "nav_github": "GitHub",
        "nav_demo": "Run the no-login Demo",
        "eyebrow": "Five decisions · five worked examples",
        "headline": "Start with the decision you need to make",
        "subhead": "See how the same evidence discipline changes the question, source review, and next action for five common research goals.",
        "choose": "Choose a research scenario",
        "view": "Open the worked example →",
        "example_decision": "Illustrative decision",
        "synthetic": "Synthetic example — no live platform data or customer result is shown.",
        "trust": ["One topic", "One platform", "Counterevidence required", "Local-first outputs"],
        "method_eyebrow": "What stays consistent",
        "method_title": "Different business questions. The same evidence boundary.",
        "method_body": "Each live study freezes scope, collects or imports platform-native signals, reviews relevance and counterexamples, then recommends a bounded next test.",
        "steps": [
            ("01", "Define", "One topic, one platform, and the decision this research must support."),
            ("02", "Collect", "Public or authorized signals with source, time, and visible context."),
            ("03", "Review", "Relevance, opened sources, representative comments, and counterevidence."),
            ("04", "Decide", "A direct answer, evidence limits, and the smallest useful next test."),
        ],
        "footer": "Independent, local-first, and MIT licensed. No default telemetry.",
        "back": "All cases",
        "platform": "Example platform",
        "status": "Current route status",
        "topic": "Research topic",
        "why": "What this case demonstrates",
        "decision_label": "Example decision brief",
        "collect_label": "What a live study must collect",
        "counter_label": "What could overturn the decision",
        "test_label": "Smallest next test",
        "prompt_label": "Use this request with the Skill",
        "cta_title": "Ready to try your own topic?",
        "cta_body": "Run the synthetic Demo first, or install the Skill and replace this example with one topic and one platform you actually need to decide on.",
        "download": "Download the latest Skill",
        "source": "View the source",
        "discuss": "Ask a usage question",
        "privacy": "These pages contain no trackers, login state, customer data, or live platform captures.",
    },
    "zh": {
        "locale": "zh-CN",
        "title": "趋势机会雷达案例库",
        "description": "五个合成案例展示同一个证据型 Agent Skill 如何支持商业、品牌、竞品、内容与产品决策。",
        "language": "English",
        "brand": "趋势机会雷达",
        "nav_cases": "案例",
        "nav_github": "GitHub",
        "nav_demo": "运行免登录 Demo",
        "eyebrow": "五种决策 · 五个完整示例",
        "headline": "先选你要做的决定，再开始研究",
        "subhead": "看看同一套证据标准，如何根据五种常见研究目的改变问题、证据检查和下一步行动。",
        "choose": "选择一个研究场景",
        "view": "查看完整示例 →",
        "example_decision": "示例判断",
        "synthetic": "合成示例——不包含真实平台数据，也不代表客户成果。",
        "trust": ["一个主题", "一个平台", "必须检查反证", "报告保存在本地"],
        "method_eyebrow": "始终不变的部分",
        "method_title": "业务问题可以变化，证据边界不能变化。",
        "method_body": "每次真实研究都会冻结范围，采集或导入平台原生信号，检查相关性、原文与反例，再提出边界清晰的下一步测试。",
        "steps": [
            ("01", "说清问题", "确定一个主题、一个平台，以及这次研究要支持的决定。"),
            ("02", "采集信号", "读取公开或已授权内容，保留来源、时间和可见上下文。"),
            ("03", "核对证据", "检查相关性、原文、代表性评论和反证。"),
            ("04", "做出决定", "给出直接回答、证据边界和最小下一步测试。"),
        ],
        "footer": "独立、本地优先、MIT 开源，不启用默认遥测。",
        "back": "全部案例",
        "platform": "示例平台",
        "status": "当前路径状态",
        "topic": "研究主题",
        "why": "这个案例说明什么",
        "decision_label": "示例决策简报",
        "collect_label": "真实研究必须采集什么",
        "counter_label": "什么情况会推翻判断",
        "test_label": "最小下一步测试",
        "prompt_label": "用这句话调用 Skill",
        "cta_title": "准备研究自己的主题？",
        "cta_body": "可以先运行合成 Demo，也可以安装 Skill，把这个示例换成你真正需要决策的一个主题和一个平台。",
        "download": "下载最新版 Skill",
        "source": "查看源代码",
        "discuss": "提一个使用问题",
        "privacy": "这些页面不包含追踪器、登录状态、客户数据或真实平台截图。",
    },
}


def load_gallery(path: Path = DATA_PATH) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "trend-radar-case-gallery-v0.1":
        raise ValueError("Unsupported case-gallery schema.")
    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != 5:
        raise ValueError("The public gallery requires exactly five decision cases.")
    slugs: set[str] = set()
    modes: set[str] = set()
    for item in cases:
        slug = str(item.get("slug") or "")
        mode = str(item.get("mode") or "")
        if not slug or slug in slugs or mode not in ALLOWED_MODES or mode in modes:
            raise ValueError("Case slugs and decision modes must be unique and complete.")
        if not isinstance(item.get("platform_status"), dict):
            raise ValueError(f"Missing platform status for {slug}.")
        for language in ("en", "zh"):
            content = item.get(language)
            required = {"name", "topic", "question", "decision", "why", "collect", "counter", "test", "prompt"}
            if not isinstance(content, dict) or not required.issubset(content):
                raise ValueError(f"Incomplete {language} content for {slug}.")
            if not isinstance(content["collect"], list) or len(content["collect"]) < 3:
                raise ValueError(f"Each case needs at least three evidence requirements: {slug}.")
        slugs.add(slug)
        modes.add(mode)
    if modes != ALLOWED_MODES:
        raise ValueError("The gallery must cover all five decision modes exactly once.")
    return value


def tracked_url(target: str, campaign: str, content: str) -> str:
    separator = "&" if "?" in target else "?"
    query = urlencode(
        {
            "utm_source": "github_pages",
            "utm_medium": "case_gallery",
            "utm_campaign": campaign,
            "utm_content": content,
        }
    )
    return f"{target}{separator}{query}"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def page_shell(*, language: str, title: str, description: str, canonical: str, alternate: str, depth: int, body: str) -> str:
    ui = UI[language]
    css = "../" * depth + "site.css"
    language_link = "zh-CN/" if language == "en" and depth == 0 else (
        "../" if language == "zh" and depth == 1 else (
            f"../zh-CN/cases/{canonical.rsplit('/', 1)[-1]}" if language == "en" else f"../../cases/{canonical.rsplit('/', 1)[-1]}"
        )
    )
    home = "../" * depth or "./"
    return f"""<!doctype html>
<html lang="{ui['locale']}" data-synthetic="true">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{esc(canonical)}">
  <link rel="alternate" hreflang="{'zh-CN' if language == 'en' else 'en'}" href="{esc(alternate)}">
  <link rel="stylesheet" href="{esc(css)}">
</head>
<body>
  <nav class="wrap site-nav" aria-label="Primary">
    <a class="brand" href="{esc(home)}"><span class="brand-dot" aria-hidden="true"></span>{esc(ui['brand'])}</a>
    <div class="nav-links">
      <a href="{esc(home)}">{esc(ui['nav_cases'])}</a>
      <a href="{esc(language_link)}" hreflang="{'zh-CN' if language == 'en' else 'en'}">{esc(ui['language'])}</a>
      <a href="{esc(REPOSITORY_URL)}">{esc(ui['nav_github'])}</a>
    </div>
  </nav>
  {body}
  <footer><div class="wrap footer-row"><span>{esc(ui['footer'])}</span><span>{esc(ui['synthetic'])}</span></div></footer>
</body>
</html>
"""


def render_hub(gallery: dict, language: str) -> str:
    ui = UI[language]
    prefix = ""
    cards: list[str] = []
    for index, item in enumerate(gallery["cases"], 1):
        content = item[language]
        cards.append(
            f"""<a class="case-card" data-accent="{esc(item['accent'])}" href="{prefix}cases/{esc(item['slug'])}.html">
  <div class="case-number"><span>{index:02d}</span><span>{esc(item['platform'])}</span></div>
  <h2>{esc(content['name'])}</h2>
  <p class="question">{esc(content['question'])}</p>
  <div class="decision-preview"><span>{esc(ui['example_decision'])}</span><p>{esc(content['decision'])}</p></div>
  <span class="card-arrow">{esc(ui['view'])}</span>
</a>"""
        )
    steps = "".join(
        f'<article class="step"><b>{esc(number)} · {esc(name)}</b><p>{esc(copy)}</p></article>'
        for number, name, copy in ui["steps"]
    )
    trust = "".join(f"<span>{esc(item)}</span>" for item in ui["trust"])
    demo_command = "py -3 skills/trend-opportunity-radar/scripts/trend_radar.py demo --language zh-CN --output-dir ./trend-radar-demo" if language == "zh" else "python3 skills/trend-opportunity-radar/scripts/trend_radar.py demo --output-dir ./trend-radar-demo"
    body = f"""<main>
  <section class="wrap hero">
    <div class="eyebrow">{esc(ui['eyebrow'])}</div>
    <h1>{esc(ui['headline'])}</h1>
    <p>{esc(ui['subhead'])}</p>
    <div class="hero-actions">
      <a class="button primary" href="#cases">{esc(ui['choose'])}</a>
      <a class="button" href="{esc(tracked_url(REPOSITORY_URL, gallery['campaign'], 'hub_demo'))}">{esc(ui['nav_demo'])}</a>
    </div>
    <div class="trust-strip">{trust}</div>
  </section>
  <section id="cases" class="wrap gallery" aria-label="{esc(ui['choose'])}">{''.join(cards)}</section>
  <section class="method">
    <div class="wrap">
      <div class="section-head"><span class="eyebrow">{esc(ui['method_eyebrow'])}</span><h2>{esc(ui['method_title'])}</h2><p>{esc(ui['method_body'])}</p></div>
      <div class="steps">{steps}</div>
      <div class="panel" style="margin-top:18px"><span class="case-index">{esc(ui['nav_demo'])}</span><div class="prompt-box">{esc(demo_command)}</div></div>
    </div>
  </section>
</main>"""
    path = "" if language == "en" else "/zh-CN"
    alternate = f"{PUBLIC_ROOT}/zh-CN/" if language == "en" else f"{PUBLIC_ROOT}/"
    return page_shell(
        language=language,
        title=ui["title"],
        description=ui["description"],
        canonical=f"{PUBLIC_ROOT}{path}/",
        alternate=alternate,
        depth=0 if language == "en" else 1,
        body=body,
    )


def render_case(gallery: dict, item: dict, language: str) -> str:
    ui = UI[language]
    content = item[language]
    depth = 1 if language == "en" else 2
    home = "../" if language == "en" else "../../"
    collect = "".join(f"<li>{esc(value)}</li>" for value in content["collect"])
    repo_url = tracked_url(REPOSITORY_URL, gallery["campaign"], item["slug"])
    release_url = tracked_url(RELEASE_URL, gallery["campaign"], f"{item['slug']}_download")
    discuss_url = tracked_url(DISCUSSIONS_URL, gallery["campaign"], f"{item['slug']}_discussion")
    body = f"""<main>
  <section class="wrap case-hero">
    <div class="crumbs"><a href="{home}">← {esc(ui['back'])}</a></div>
    <div class="synthetic-banner" role="note">{esc(ui['synthetic'])}</div>
    <span class="case-index">{esc(content['name'])}</span>
    <h1>{esc(content['question'])}</h1>
    <p class="lead">{esc(content['why'])}</p>
    <div class="case-meta"><span class="pill">{esc(ui['platform'])}: {esc(item['platform'])}</span><span class="pill">{esc(ui['status'])}: {esc(item['platform_status'][language])}</span><span class="pill">{esc(ui['topic'])}: {esc(content['topic'])}</span></div>
  </section>
  <section class="wrap case-layout">
    <div class="stack">
      <article class="panel decision-panel"><span class="case-index">{esc(ui['decision_label'])}</span><h2>{esc(content['decision'])}</h2><p>{esc(content['why'])}</p></article>
      <article class="panel"><span class="case-index">{esc(ui['collect_label'])}</span><h2>{esc(ui['collect_label'])}</h2><ul class="evidence-list">{collect}</ul></article>
      <article class="panel boundary"><span class="case-index">{esc(ui['counter_label'])}</span><h2>{esc(ui['counter_label'])}</h2><p>{esc(content['counter'])}</p></article>
      <article class="panel next-test"><span class="case-index">{esc(ui['test_label'])}</span><h2>{esc(ui['test_label'])}</h2><p>{esc(content['test'])}</p></article>
      <article class="panel"><span class="case-index">{esc(ui['prompt_label'])}</span><h2>{esc(ui['prompt_label'])}</h2><div class="prompt-box">{esc(content['prompt'])}</div></article>
    </div>
    <aside><div class="panel side-cta"><span class="case-index">{esc(ui['cta_title'])}</span><h2>{esc(ui['cta_title'])}</h2><p>{esc(ui['cta_body'])}</p><a class="button primary" href="{esc(release_url)}">{esc(ui['download'])}</a><a class="button" href="{esc(repo_url)}">{esc(ui['source'])}</a><a class="button" href="{esc(discuss_url)}">{esc(ui['discuss'])}</a><p class="microcopy">{esc(ui['privacy'])}</p></div></aside>
  </section>
</main>"""
    language_path = "" if language == "en" else "/zh-CN"
    other_path = "/zh-CN" if language == "en" else ""
    filename = f"{item['slug']}.html"
    return page_shell(
        language=language,
        title=f"{content['name']} — {ui['brand']}",
        description=f"{content['question']} {content['decision']}",
        canonical=f"{PUBLIC_ROOT}{language_path}/cases/{filename}",
        alternate=f"{PUBLIC_ROOT}{other_path}/cases/{filename}",
        depth=depth,
        body=body,
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")


def build(output_dir: Path, data_path: Path = DATA_PATH) -> dict:
    gallery = load_gallery(data_path)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_text(output_dir / "index.html", render_hub(gallery, "en"))
    write_text(output_dir / "zh-CN" / "index.html", render_hub(gallery, "zh"))
    for item in gallery["cases"]:
        write_text(output_dir / "cases" / f"{item['slug']}.html", render_case(gallery, item, "en"))
        write_text(output_dir / "zh-CN" / "cases" / f"{item['slug']}.html", render_case(gallery, item, "zh"))
    shutil.copyfile(CSS_PATH, output_dir / "site.css")
    write_text(output_dir / ".nojekyll", "")
    urls = [f"{PUBLIC_ROOT}/", f"{PUBLIC_ROOT}/zh-CN/"]
    for item in gallery["cases"]:
        urls.extend(
            [
                f"{PUBLIC_ROOT}/cases/{item['slug']}.html",
                f"{PUBLIC_ROOT}/zh-CN/cases/{item['slug']}.html",
            ]
        )
    sitemap = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n" + "".join(
        f"  <url><loc>{esc(url)}</loc></url>\n" for url in urls
    ) + "</urlset>\n"
    write_text(output_dir / "sitemap.xml", sitemap)
    write_text(output_dir / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {PUBLIC_ROOT}/sitemap.xml\n")
    return {"output_dir": str(output_dir), "case_count": 5, "page_count": len(urls), "synthetic": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the bilingual synthetic case gallery for GitHub Pages.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, args.data), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
