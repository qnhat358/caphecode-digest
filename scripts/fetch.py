#!/usr/bin/env python3
"""Lấy tin từ các nguồn trong config/sources.json, gộp tin trùng, ghi ra out/candidates.json.

Chỉ dùng thư viện chuẩn. Nguồn nào lỗi thì ghi vào "errors" và bỏ qua, không làm hỏng cả lượt chạy.
"""
import html
import json
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 daily-tech-digest/1.0")


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        # Vài trang (Reddit) treo bắt tay TLS với Python nhưng cho curl qua; curl cũng là lần thử lại khi lỗi thoáng qua.
        return subprocess.run(["curl", "-sfL", "--compressed", "-m", str(timeout), "-A", UA, url],
                              capture_output=True, check=True).stdout


def clean(text, limit=300):
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def parse_date(value):
    if not value:
        return None
    try:
        d = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def item(title, url, discussion=None, score=None, comments=None, published=None, snippet="", **extra):
    return {"title": clean(title, 200), "url": url, "discussion": discussion, "score": score,
            "comments": comments, "published": published.isoformat() if published else None,
            "snippet": clean(snippet), **extra}


def hn(src, since):
    url = ("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=100"
           f"&numericFilters=created_at_i>{int(since.timestamp())},points>{src.get('min_points', 80)}")
    hits = sorted(json.loads(get(url))["hits"], key=lambda h: h["points"], reverse=True)
    out = []
    for h in hits:
        thread = f"https://news.ycombinator.com/item?id={h['objectID']}"
        out.append(item(h["title"], h.get("url") or thread, thread, h["points"], h.get("num_comments"),
                        datetime.fromtimestamp(h["created_at_i"], timezone.utc), h.get("story_text") or ""))
    return out


def lobsters(src, since):
    out = []
    for s in json.loads(get("https://lobste.rs/hottest.json")):
        published = parse_date(s.get("created_at"))
        if published and published < since:
            continue
        out.append(item(s["title"], s.get("url") or s["comments_url"], s["comments_url"], s.get("score"),
                        s.get("comment_count"), published, s.get("description_plain", ""), tags=s.get("tags")))
    return out


def reddit(src, since):
    # Reddit chặn JSON công khai (403) và rate limit rất gắt, nên gộp mọi subreddit vào một request RSS.
    # RSS không có điểm; thứ tự là top trong ngày.
    found = rss({"url": f"https://www.reddit.com/r/{'+'.join(src['subreddits'])}/top/.rss?t=day&limit=50"}, since)
    for rank, it in enumerate(found, 1):
        sub = re.search(r"/r/([^/]+)/", it["url"])
        it.update(discussion=it["url"], rank=rank, subreddit=sub.group(1) if sub else None)
    return found


def github_trending(src, since):
    page = get("https://github.com/trending?since=daily").decode("utf-8", "replace")
    out = []
    for block in page.split('<article class="Box-row">')[1:]:
        repo = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"', block)
        if not repo:
            continue
        desc = re.search(r'<p class="col-9[^"]*">(.*?)</p>', block, re.S)
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', block)
        today = re.search(r"([\d,]+) stars? today", block)
        out.append(item(repo.group(1), f"https://github.com/{repo.group(1)}",
                        score=int(today.group(1).replace(",", "")) if today else None,
                        snippet=desc.group(1) if desc else "", language=lang.group(1) if lang else None))
    return out


def hf_papers(src, since):
    papers = json.loads(get("https://huggingface.co/api/daily_papers?limit=30"))
    out = []
    for p in papers:
        paper = p.get("paper", p)
        out.append(item(paper.get("title") or p.get("title", ""), f"https://huggingface.co/papers/{paper['id']}",
                        score=paper.get("upvotes"), published=parse_date(p.get("publishedAt")),
                        snippet=paper.get("summary", "")))
    return sorted(out, key=lambda i: i["score"] or 0, reverse=True)


def rss(src, since):
    root = ET.fromstring(get(src["url"]))
    for el in root.iter():  # bỏ namespace cho dễ tìm thẻ
        el.tag = el.tag.split("}", 1)[-1]
    out = []
    for entry in root.iter("item") if root.find(".//item") is not None else root.iter("entry"):
        link = entry.find("link")
        url = (link.get("href") or link.text or "").strip() if link is not None else ""
        date = (entry.findtext("pubDate") or entry.findtext("published") or entry.findtext("updated")
                or entry.findtext("date"))
        published = parse_date(date)
        if published is None or published < since:
            continue
        snippet = entry.findtext("description") or entry.findtext("summary") or entry.findtext("content") or ""
        out.append(item(entry.findtext("title") or "", url, published=published, snippet=snippet))
    return out


FETCHERS = {"hn": hn, "lobsters": lobsters, "reddit": reddit, "github_trending": github_trending,
            "hf_papers": hf_papers, "rss": rss}


def norm(url):
    parts = urlsplit(url or "")
    host = parts.netloc.lower().removeprefix("www.")
    return urlunsplit(("", host, parts.path.rstrip("/"), parts.query, ""))


def main():
    config = json.loads((ROOT / "config/sources.json").read_text())
    since = datetime.now(timezone.utc) - timedelta(hours=config.get("hours", 26))
    limit = config.get("max_per_source", 15)

    def run(src):
        for attempt in range(2):
            try:
                return src, FETCHERS[src["type"]](src, since)[:limit], None
            except Exception as e:  # noqa: BLE001 — thử lại một lần, vẫn lỗi thì bỏ qua nguồn này
                error = f"{type(e).__name__}: {e}"
                time.sleep(3)
        return src, [], error

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, config["sources"]))

    items, seen, errors = [], {}, []
    for src, found, error in results:
        print(f"{src['name']:<24} {'LỖI ' + error if error else len(found)}", file=sys.stderr)
        if error:
            errors.append({"source": src["name"], "error": error})
        for it in found:
            key = norm(it["url"])
            if key in seen:  # cùng một link ở nhiều nguồn: giữ bản đầu, ghi thêm nơi xuất hiện
                seen[key].setdefault("also_on", []).append(
                    {"source": src["name"], "discussion": it["discussion"], "score": it["score"]})
                continue
            it["source"] = src["name"]
            seen[key] = it
            items.append(it)

    out = ROOT / "out/candidates.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "since": since.isoformat(),
                               "errors": errors, "items": items}, ensure_ascii=False, indent=1))
    print(f"\n{len(items)} tin, {len(errors)} nguồn lỗi -> {out.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
