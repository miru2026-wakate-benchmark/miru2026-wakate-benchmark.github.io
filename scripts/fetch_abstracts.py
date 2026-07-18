#!/usr/bin/env python3
"""Fetch source abstracts for the papers currently exposed by papers.js.

This is a research/update helper. It writes raw source text for review; the public
site uses the separately curated Japanese summaries in abstracts_ja.json.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "MIRU2026BenchmarkSurvey/1.0 (academic abstract curation)"


class AbstractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_candidates: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag != "meta":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        name = (values.get("name") or values.get("property") or "").lower()
        content = values.get("content", "").strip()
        priorities = {
            "citation_abstract": 0,
            "dc.description": 1,
            "dcterms.abstract": 1,
            "og:description": 2,
            "description": 3,
        }
        if content and name in priorities:
            self.meta_candidates.append((priorities[name], content))


def clean_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(abstract\s*[:.—-]?\s*)", "", value, flags=re.I)
    return value


def source_url(url: str) -> str:
    arxiv = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", url, re.I)
    if arxiv:
        return f"https://arxiv.org/abs/{arxiv.group(1)}"
    arxiv_doi = re.search(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})", url, re.I)
    if arxiv_doi:
        return f"https://arxiv.org/abs/{arxiv_doi.group(1)}"
    return url


def fetch_openreview(url: str) -> str:
    forum = parse_qs(urlparse(url).query).get("id", [""])[0]
    if not forum:
        return ""
    api = f"https://api2.openreview.net/notes?forum={quote(forum)}"
    request = Request(api, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    for note in payload.get("notes", []):
        abstract = note.get("content", {}).get("abstract", "")
        if isinstance(abstract, dict):
            abstract = abstract.get("value", "")
        if isinstance(abstract, str) and len(clean_text(abstract)) > 80:
            return clean_text(abstract)
    return ""


def normalized_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def fetch_arxiv_by_title(title: str) -> tuple[str, str]:
    query = urlencode({"search_query": f'ti:"{title}"', "start": 0, "max_results": 5})
    url = f"https://export.arxiv.org/api/query?{query}"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml"})
    try:
        with urlopen(request, timeout=35) as response:
            root = ET.fromstring(response.read())
    except (HTTPError, URLError, TimeoutError, ValueError, ET.ParseError):
        return "", ""
    atom = {"a": "http://www.w3.org/2005/Atom"}
    wanted = normalized_title(title)
    entries = root.findall("a:entry", atom)
    entries.sort(
        key=lambda entry: normalized_title(entry.findtext("a:title", "", atom)) != wanted
    )
    for entry in entries:
        found_title = entry.findtext("a:title", "", atom)
        if wanted not in normalized_title(found_title) and normalized_title(found_title) not in wanted:
            continue
        abstract = clean_text(entry.findtext("a:summary", "", atom))
        source = entry.findtext("a:id", "", atom)
        if len(abstract) > 80:
            return abstract, source
    return "", ""


def fetch_one(paper: dict[str, str]) -> dict[str, str]:
    url = source_url(paper["url"])
    try:
        if "openreview.net" in url:
            abstract = fetch_openreview(url)
            if abstract:
                return {"title": paper["title"], "url": paper["url"], "source": url, "abstract": abstract, "error": ""}

        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urlopen(request, timeout=35) as response:
            body = response.read(4_000_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
            final_url = response.geturl()
        parser = AbstractParser()
        parser.feed(body)
        candidates = sorted(parser.meta_candidates, key=lambda item: item[0])
        abstract = next((clean_text(text) for _, text in candidates if len(clean_text(text)) > 80), "")
        if not abstract:
            patterns = [
                r'<blockquote[^>]*class="abstract[^>]*>(.*?)</blockquote>',
                r'<div[^>]*(?:id|class)="[^"]*abstract[^"]*"[^>]*>(.*?)</div>',
            ]
            for pattern in patterns:
                matched = re.search(pattern, body, re.I | re.S)
                if matched:
                    abstract = clean_text(re.sub(r"<[^>]+>", " ", matched.group(1)))
                    if len(abstract) > 80:
                        break
        if not abstract:
            abstract, arxiv_source = fetch_arxiv_by_title(paper["title"])
            if abstract:
                final_url = arxiv_source
        error = "" if abstract else "abstract metadata not found"
        return {"title": paper["title"], "url": paper["url"], "source": final_url, "abstract": abstract, "error": error}
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        abstract, arxiv_source = fetch_arxiv_by_title(paper["title"])
        if abstract:
            return {"title": paper["title"], "url": paper["url"], "source": arxiv_source, "abstract": abstract, "error": ""}
        return {"title": paper["title"], "url": paper["url"], "source": url, "abstract": "", "error": str(exc)}


def load_papers(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    payload = re.sub(r"^//.*?\nwindow\.PAPERS = ", "", text, flags=re.S).rsplit(";", 1)[0]
    return json.loads(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("papers_js", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    papers = load_papers(args.papers_js)
    results: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_one, paper): paper for paper in papers}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "ok" if result["abstract"] else f"missing: {result['error']}"
            print(f"[{len(results):02}/{len(papers)}] {status} — {result['title']}")
            time.sleep(0.03)
    order = {paper["title"]: index for index, paper in enumerate(papers)}
    results.sort(key=lambda item: order[item["title"]])
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    found = sum(bool(item["abstract"]) for item in results)
    print(f"Wrote {found}/{len(results)} abstracts to {args.output}")


if __name__ == "__main__":
    main()
