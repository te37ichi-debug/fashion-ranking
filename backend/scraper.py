import asyncio
import re
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_rss(url: str) -> list[dict]:
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries:
            items.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
                "image": "",
            })
        return items
    except Exception:
        return []


def _get_disallowed_paths(base_url: str) -> set[str]:
    """Fetch robots.txt and return disallowed paths for *."""
    try:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        resp = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=10)
        if resp.status_code != 200:
            return set()

        disallowed = set()
        applies = False
        for line in resp.text.splitlines():
            line = line.strip()
            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                applies = agent == "*"
            elif applies and line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    disallowed.add(path)
        return disallowed
    except Exception:
        return set()


def _is_allowed(url: str, disallowed_paths: set[str]) -> bool:
    """Check if url path is not blocked by robots.txt disallow rules."""
    path = urlparse(url).path
    for d in disallowed_paths:
        if path.startswith(d):
            return False
    return True


MAX_ITEMS = 30
CONTENT_CLASSES = re.compile(r"article|post|item|product|card", re.IGNORECASE)
ARTICLE_PATH_PATTERN = re.compile(r"/(article|news|item|product|post|feature)/", re.IGNORECASE)
ARTICLE_DATE_PATTERN = re.compile(r"/article/20\d{2}[-/]")


def _normalize_url(href: str, base_url: str) -> str | None:
    """Resolve href to absolute URL, strip fragment. Return None if off-domain."""
    full = urljoin(base_url, href)
    parsed = urlparse(full)
    base_domain = urlparse(base_url).netloc
    if parsed.netloc != base_domain:
        return None
    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        clean += f"?{parsed.query}"
    return clean


def _extract_links(
    a_tags: list,
    base_url: str,
    disallowed: set[str],
    seen: set[str],
    min_text_len: int = 1,
) -> list[dict]:
    """Extract deduplicated same-domain link dicts from a list of <a> tags."""
    results = []
    for a_tag in a_tags:
        href = a_tag.get("href")
        if not href:
            continue
        clean_url = _normalize_url(href, base_url)
        if not clean_url or clean_url == base_url or clean_url in seen:
            continue
        if not _is_allowed(clean_url, disallowed):
            continue
        text = a_tag.get_text(strip=True)
        if len(text) < min_text_len:
            continue
        seen.add(clean_url)
        results.append({"title": text, "url": clean_url, "summary": "", "published": "", "image": ""})
        if len(results) >= MAX_ITEMS:
            break
    return results


def fetch_static(url: str) -> list[dict]:
    try:
        disallowed = _get_disallowed_paths(url)

        if not _is_allowed(url, disallowed):
            return []

        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # OGP info
        og_title = ""
        og_desc = ""
        og_image = ""
        tag = soup.find("meta", property="og:title")
        if tag:
            og_title = tag.get("content", "")
        tag = soup.find("meta", property="og:description")
        if tag:
            og_desc = tag.get("content", "")
        tag = soup.find("meta", property="og:image")
        if tag:
            og_image = tag.get("content", "")

        page_title = soup.title.string.strip() if soup.title and soup.title.string else ""

        all_a = soup.find_all("a", href=True)[:250]
        seen: set[str] = set()
        items: list[dict] = []

        # Strategy 0: /article/YYYY date pattern links (fashionsnap etc.)
        if not items:
            for a_tag in all_a:
                if len(items) >= MAX_ITEMS:
                    break
                href = a_tag.get("href", "")
                full = urljoin(url, href)
                path = urlparse(full).path
                if not ARTICLE_DATE_PATTERN.search(path):
                    continue
                clean_url = _normalize_url(href, url)
                if not clean_url or clean_url in seen or clean_url == url:
                    continue
                if not _is_allowed(clean_url, disallowed):
                    continue
                # Try text from <a>, then parent, then URL slug
                text = a_tag.get_text(strip=True)
                if not text and a_tag.parent:
                    text = a_tag.parent.get_text(strip=True)
                if not text:
                    slug = path.rstrip("/").rsplit("/", 1)[-1]
                    text = slug.replace("-", " ")
                if not text:
                    continue
                seen.add(clean_url)
                items.append({"title": text, "url": clean_url, "summary": "", "published": "", "image": ""})

        # Strategy 1: <a> with article-like URL path pattern (text >= 15 chars)
        if not items:
            matched = []
            for a_tag in all_a:
                href = a_tag.get("href", "")
                full = urljoin(url, href)
                if ARTICLE_PATH_PATTERN.search(urlparse(full).path):
                    matched.append(a_tag)
            items = _extract_links(matched, url, disallowed, seen, min_text_len=15)

        # Strategy 2: <a> inside <article> tags
        if not items:
            a_tags = []
            for article in soup.find_all("article"):
                a_tags.extend(article.find_all("a", href=True))
            items = _extract_links(a_tags, url, disallowed, seen)

        # Strategy 3: <a> inside <h1>/<h2>/<h3> tags
        if not items:
            a_tags = []
            for heading in soup.find_all(["h1", "h2", "h3"]):
                a_tags.extend(heading.find_all("a", href=True))
            items = _extract_links(a_tags, url, disallowed, seen)

        # Strategy 4: <a> inside elements with content-related class names
        if not items:
            a_tags = []
            for el in soup.find_all(class_=CONTENT_CLASSES):
                a_tags.extend(el.find_all("a", href=True))
            items = _extract_links(a_tags, url, disallowed, seen)

        # Strategy 5: all <a> tags with text >= 15 chars
        if not items:
            items = _extract_links(all_a, url, disallowed, seen, min_text_len=15)

        # Attach OGP info to first item
        if items:
            items[0]["summary"] = og_desc
            items[0]["image"] = og_image

        # Fallback: page itself
        if not items and page_title:
            items.append({
                "title": og_title or page_title,
                "url": url,
                "summary": og_desc,
                "published": "",
                "image": og_image,
            })

        return items[:MAX_ITEMS]
    except Exception:
        return []


async def _get_dynamic_html(url: str) -> str:
    """Launch Playwright, load page, return rendered HTML."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            html = await page.content()
        finally:
            await browser.close()
    return html


async def fetch_dynamic(url: str) -> list[dict]:
    try:
        html = await _get_dynamic_html(url)
        soup = BeautifulSoup(html, "html.parser")

        # OGP info
        og_desc = ""
        og_image = ""
        tag = soup.find("meta", property="og:title")
        og_title = tag.get("content", "") if tag else ""
        tag = soup.find("meta", property="og:description")
        if tag:
            og_desc = tag.get("content", "")
        tag = soup.find("meta", property="og:image")
        if tag:
            og_image = tag.get("content", "")
        page_title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # Extract article links
        seen: set[str] = set()
        items: list[dict] = []

        for a in soup.find_all("a", href=True):
            if len(items) >= MAX_ITEMS:
                break
            href = a.get("href", "")
            if "/article/20" not in href:
                continue
            clean_url = _normalize_url(href, url)
            if not clean_url or clean_url in seen or clean_url == url:
                continue

            text = a.get_text(strip=True)
            if not text:
                parent = a.find_parent(["div", "li", "article"])
                if parent:
                    text = parent.get_text(strip=True)[:50]
            if not text:
                slug = urlparse(clean_url).path.rstrip("/").rsplit("/", 1)[-1]
                text = slug.replace("-", " ")
            if not text:
                continue

            seen.add(clean_url)
            items.append({
                "title": text[:200],
                "url": clean_url,
                "summary": "",
                "published": "",
                "image": og_image,
            })

        if items:
            items[0]["summary"] = og_desc

        if not items and page_title:
            items.append({
                "title": og_title or page_title,
                "url": url,
                "summary": og_desc,
                "published": "",
                "image": og_image,
            })

        return items[:MAX_ITEMS]
    except Exception:
        return []


def debug_fetch(url: str) -> dict:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, timeout=10, headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")

    title = str(soup.title) if soup.title else None
    all_a = soup.find_all("a", href=True)
    sample = [
        {"href": a.get("href"), "text": a.get_text(strip=True)[:50]}
        for a in all_a[:50]
    ]

    article_count = len(soup.find_all("article"))
    heading_a_count = sum(
        len(h.find_all("a", href=True)) for h in soup.find_all(["h1", "h2", "h3"])
    )
    class_a_count = sum(
        len(el.find_all("a", href=True)) for el in soup.find_all(class_=CONTENT_CLASSES)
    )

    return {
        "title": title,
        "a_tag_count": len(all_a),
        "a_tag_sample": sample,
        "article_tag_count": article_count,
        "heading_a_count": heading_a_count,
        "content_class_a_count": class_a_count,
    }


async def debug_fetch_dynamic(url: str) -> dict:
    html = await _get_dynamic_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    tag = soup.find("meta", property="og:image")
    og_image = tag.get("content", "") if tag else ""

    all_a = soup.find_all("a", href=True)
    sample = [
        {"href": a.get("href"), "text": a.get_text(strip=True)[:100]}
        for a in all_a[:50]
    ]

    return {
        "title": title,
        "a_tag_count": len(all_a),
        "a_tag_sample": sample,
        "og_image": og_image,
    }
