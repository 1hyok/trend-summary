import os
import re
from urllib.parse import quote, urljoin

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_rss(source):
    feed = feedparser.parse(source["url"])
    return [
        {
            "source": source["name"],
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
        }
        for entry in feed.entries
    ]


def fetch_youtube(source):
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return []
    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": source.get("region_code", "KR"),
            "maxResults": source.get("max_results", 20),
            "key": api_key,
        },
        timeout=10,
    )
    resp.raise_for_status()
    items = []
    for v in resp.json().get("items", []):
        snip = v.get("snippet", {})
        items.append(
            {
                "source": source["name"],
                "title": snip.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "channel": snip.get("channelTitle", ""),
                "view_count": v.get("statistics", {}).get("viewCount", ""),
            }
        )
    return items


def fetch_scrape(source):
    resp = requests.get(
        source["url"],
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        },
        timeout=10,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    url_pattern = source.get("url_pattern")
    selector = source.get("selector")
    if url_pattern:
        anchors = soup.find_all("a", href=re.compile(url_pattern))
    elif selector:
        anchors = soup.select(selector)
    else:
        anchors = soup.find_all("a")

    items = []
    seen = set()
    for a in anchors:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if not (5 < len(title) < 200 and href):
            continue
        if title in seen:
            continue
        seen.add(title)
        items.append(
            {
                "source": source["name"],
                "title": title,
                "url": urljoin(source["url"], href),
            }
        )
    return items[:30]


def fetch_namuwiki_sidebar(source):
    url = source.get("url", "https://namu.wiki/sidebar.json")
    resp = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    seen = set()
    for entry in data:
        doc = entry.get("document", "")
        if not doc or doc in seen:
            continue
        seen.add(doc)
        items.append(
            {
                "source": source["name"],
                "title": doc,
                "url": f"https://namu.wiki/w/{quote(doc, safe=':/')}",
            }
        )
    return items[:30]


def fetch_og_data(url, timeout=3):
    """Fetch og:image / og:title / og:description from a URL. Returns dict with empty strings on failure."""
    result = {"image": "", "title": "", "description": ""}
    if not url or not url.startswith(("http://", "https://")):
        return result
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=timeout,
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return result
        soup = BeautifulSoup(resp.text, "html.parser")
        for key, prop in [("image", "og:image"), ("title", "og:title"), ("description", "og:description")]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag:
                result[key] = (tag.get("content") or "").strip()
        if not result["image"]:
            tw = soup.find("meta", attrs={"name": "twitter:image"})
            if tw:
                result["image"] = (tw.get("content") or "").strip()
    except Exception:
        pass
    return result


def collect_all(config_path="config.yaml"):
    config = load_config(config_path)
    all_items = []
    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue
        try:
            if source["type"] == "rss":
                items = fetch_rss(source)
            elif source["type"] == "youtube":
                items = fetch_youtube(source)
            elif source["type"] == "scrape":
                items = fetch_scrape(source)
            elif source["type"] == "namuwiki_sidebar":
                items = fetch_namuwiki_sidebar(source)
            else:
                continue
            all_items.extend(items)
        except Exception as e:
            print(f"[collector] {source['name']} failed: {e}")
    return all_items


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    items = collect_all()
    print(f"Collected {len(items)} items total")
    by_source = {}
    for item in items:
        by_source.setdefault(item["source"], []).append(item)
    for source_name, source_items in by_source.items():
        print(f"\n[{source_name}] {len(source_items)} items")
        for item in source_items[:3]:
            print(f"  - {item['title'][:80]}")
