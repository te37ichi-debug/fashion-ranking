#!/usr/bin/env python3
"""
ブランド新着情報&人気ランキング Bot
ブランドごとの新着・人気アイテムを取得・保存するスクリプト
"""

import json
import os
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "data")
REPO_DIR = SCRIPT_DIR
TODAY = datetime.now().strftime("%Y-%m-%d")
PAGES_URL = "https://te37ichi-debug.github.io/fashion-ranking/brands.html"
IS_CI = os.environ.get("CI") == "true"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# ScraperAPI（adidas.jp / atmos-tokyo.com のbot検知回避用）
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")

# Discord Webhook（ブランドランキング専用チャンネル）
BRAND_WEBHOOK_URL = os.environ.get("BRAND_WEBHOOK_URL", "https://discord.com/api/webhooks/1493543560463777872/UjBRzjBcRgHAWQtNuVwalFOpEr-Q5cPh2WGoLtkT1sTpewRyTY5OGfAFRyTvFXd9_gg1")


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ──────────────────────────────────────────────────────────
# ブランド定義
# ──────────────────────────────────────────────────────────

BRANDS_CONFIG = os.path.join(SCRIPT_DIR, "brands_config.json")

def load_brands():
    with open(BRANDS_CONFIG, encoding="utf-8") as f:
        brands_list = json.load(f)
    return {b["key"]: {k: v for k, v in b.items() if k != "key"} for b in brands_list}


# ──────────────────────────────────────────────────────────
# adidas
# ──────────────────────────────────────────────────────────

def _launch_stealth_browser(playwright):
    """bot検知回避用のブラウザを起動する（CI: xvfb上のGUIモード）"""
    from playwright_stealth import Stealth
    stealth = Stealth()
    # CI環境ではxvfb上でGUIモード起動（headless検知回避）
    browser = playwright.chromium.launch(
        headless=not IS_CI,
        channel=None if IS_CI else "chrome",
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=UA,
        viewport={"width": 1280, "height": 720},
        locale="ja-JP",
    )
    page = context.new_page()
    stealth.apply_stealth_sync(page)
    return browser, page


def _scraper_api_get(target_url, render=True):
    """ScraperAPI経由でページを取得する"""
    params = {
        "api_key": SCRAPER_API_KEY,
        "url": target_url,
        "country_code": "jp",
    }
    if render:
        params["render"] = "true"
    resp = requests.get("https://api.scraperapi.com", params=params, timeout=120)
    resp.raise_for_status()
    return resp.text


def fetch_adidas(max_items=20):
    print("[adidas] 新着アイテム取得中...")
    import re
    items = []

    try:
        html = _scraper_api_get("https://www.adidas.jp/new_arrivals")
        soup = BeautifulSoup(html, "html.parser")

        title = soup.title.string if soup.title else "no title"
        print(f"[adidas] ページタイトル: {title}, HTML長: {len(html)}")

        cards = soup.select("article[class*='product-card']")
        if not cards:
            cards = soup.select("[data-testid*='product'], [class*='product-card']")
        print(f"[adidas] カード数: {len(cards)}")

        seen_names = set()
        for card in cards:
            if len(items) >= max_items:
                break

            link = card.select_one("a[href]")
            href = link.get("href", "") if link else ""
            url = f"https://www.adidas.jp{href}" if href.startswith("/") else href

            name = ""
            for el in card.select("[class*='name'], [class*='Name'], [class*='title'], [class*='Title']"):
                t = el.get_text(strip=True)
                if t and len(t) > 3:
                    name = t
                    break

            if not name or name in seen_names:
                continue
            seen_names.add(name)

            category = ""
            for el in card.select("p, span"):
                t = el.get_text(strip=True)
                if "オリジナルス" in t or "メンズ" in t or "レディース" in t or "ランニング" in t:
                    category = t
                    break

            price = ""
            for el in card.select("[class*='price'], [class*='Price']"):
                t = el.get_text(strip=True)
                if "¥" in t:
                    m = re.search(r'¥[\d,]+', t)
                    if m:
                        price = m.group()
                        break

            image = ""
            img_el = card.select_one("img[src*='assets.adidas']")
            if img_el:
                image = img_el.get("src", "")

            items.append({
                "rank": len(items) + 1,
                "name": name,
                "brand": category,
                "price": price,
                "image": image,
                "url": url,
            })

    except Exception as e:
        print(f"[adidas] ScraperAPI取得失敗: {e}")

    print(f"[adidas] {len(items)} 件取得")
    return items


# ──────────────────────────────────────────────────────────
# adidas (atmos)
# ──────────────────────────────────────────────────────────

def fetch_adidas_atmos(max_items=20):
    print("[adidas (atmos)] 新着アイテム取得中...")
    import re
    items = []

    try:
        html = _scraper_api_get("https://www.atmos-tokyo.com/category/all?brand=adidas")
        soup = BeautifulSoup(html, "html.parser")

        title = soup.title.string if soup.title else "no title"
        print(f"[adidas (atmos)] ページタイトル: {title}, HTML長: {len(html)}")

        cards = soup.select("li.lists-products-item")
        if not cards:
            cards = soup.select(".product-item, .product-card")
        print(f"[adidas (atmos)] カード数: {len(cards)}")

        seen_urls = set()
        for card in cards:
            if len(items) >= max_items:
                break

            link = card.select_one("a[href]")
            href = link.get("href", "") if link else ""
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            url = href if href.startswith("http") else f"https://www.atmos-tokyo.com{href}"

            name_el = card.select_one("h2")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                continue

            price = ""
            text = card.get_text(separator="|", strip=True)
            m = re.search(r'¥[\d,]+', text)
            if m:
                price = m.group()

            image = ""
            img_el = card.select_one("img")
            if img_el:
                image = img_el.get("src", "") or img_el.get("data-src", "")

            items.append({
                "rank": len(items) + 1,
                "name": name,
                "price": price,
                "image": image,
                "url": url,
            })

    except Exception as e:
        print(f"[adidas (atmos)] ScraperAPI取得失敗: {e}")

    print(f"[adidas (atmos)] {len(items)} 件取得")
    return items


# ──────────────────────────────────────────────────────────
# Carhartt WIP
# ──────────────────────────────────────────────────────────

def fetch_carhartt(max_items=20):
    print("[Carhartt WIP] メンズ新着アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto("https://carhartt-wip.jp/collections/men-new", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select("product-card")
            seen_names = set()
            for card in cards:
                if len(items) >= max_items:
                    break

                # 商品名
                name_el = card.select_one("a.bold")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                # URL
                href = name_el.get("href", "") if name_el else ""
                url = f"https://carhartt-wip.jp{href}" if href.startswith("/") else href

                # 価格
                price = ""
                text = card.get_text(separator="|", strip=True)
                m = re.search(r'¥[\d,]+', text)
                if m:
                    price = m.group()

                # 画像
                image = ""
                img_el = card.select_one("img[alt]")
                if img_el:
                    src = img_el.get("src", "")
                    if src.startswith("//"):
                        src = "https:" + src
                    image = src

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })

        except Exception as e:
            print(f"[Carhartt WIP] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[Carhartt WIP] {len(items)} 件取得")
    return items


# ──────────────────────────────────────────────────────────
# DIESEL
# ──────────────────────────────────────────────────────────

def fetch_diesel(max_items=20):
    print("[DIESEL] メンズ新着アパレル取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto(
                "https://www.diesel.co.jp/ja/man/new-arrivals/apparel/?cgid=diesel-newin-man-features-NAapparel&prefn1=displayOnlyOnSale&prefv1=false",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select("div.product-tile")
            seen_urls = set()
            for card in cards:
                if len(items) >= max_items:
                    break

                link = card.select_one("a[href]")
                href = link.get("href", "") if link else ""
                if not href or href in seen_urls:
                    continue
                seen_urls.add(href)
                url = href if href.startswith("http") else f"https://www.diesel.co.jp{href}"

                # 商品名: テキストの最初の要素
                text = card.get_text(separator="|", strip=True)
                parts = [p.strip() for p in text.split("|") if p.strip()]
                # "responsible" などのラベルをスキップ
                name = ""
                for part in parts:
                    if part in ("responsible", "NEW"):
                        continue
                    if "¥" in part or "Colours" in part.lower():
                        break
                    name = part
                    break

                if not name:
                    continue

                # 価格
                price = ""
                m = re.search(r'¥\s*[\d,]+', text)
                if m:
                    price = m.group().replace(" ", "")

                # 画像
                image = ""
                img_el = card.select_one("img[src*='diesel']")
                if img_el:
                    image = img_el.get("src", "")

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })

        except Exception as e:
            print(f"[DIESEL] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[DIESEL] {len(items)} 件取得")
    return items


# ──────────────────────────────────────────────────────────
# SATUR
# ──────────────────────────────────────────────────────────

def fetch_satur(max_items=20):
    print("[SATUR] メンズ人気アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto("https://satur-jp.com/collections/man?sort_by=best-selling", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select("product-item")
            for card in cards:
                if len(items) >= max_items:
                    break

                title_el = card.select_one("a.product-item-meta__title")
                name = title_el.get_text(strip=True) if title_el else ""
                if not name:
                    continue

                href = title_el.get("href", "") if title_el else ""
                url = f"https://satur-jp.com{href}" if href.startswith("/") else href

                price = ""
                text = card.get_text(separator="|", strip=True)
                m = re.search(r'¥[\d,]+', text)
                if m:
                    price = m.group()

                image = ""
                img_el = card.select_one("img[src*='cdn']")
                if img_el:
                    src = img_el.get("src", "")
                    image = f"https:{src}" if src.startswith("//") else src

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })

        except Exception as e:
            print(f"[SATUR] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[SATUR] {len(items)} 件取得")
    return items


# ──────────────────────────────────────────────────────────
# BUYMA 共通パーサー
# ──────────────────────────────────────────────────────────

def _fetch_buyma_brand(label, url, max_items=20):
    """BUYMA のブランドページから人気アイテムを取得する共通関数"""
    print(f"[{label}] 人気アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(600)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select("li.product")
            seen_names = set()
            for card in cards:
                if len(items) >= max_items:
                    break

                name = ""
                item_url = ""

                # URL: item-url 属性 or リンクから
                action_el = card.select_one("[item-url]")
                if action_el:
                    iurl = action_el.get("item-url", "")
                    if iurl:
                        item_url = f"https://www.buyma.com{iurl}" if iurl.startswith("/") else iurl

                name_el = card.select_one("h2.name a") or card.select_one("a[data-ga-item-name]")
                if name_el:
                    name = name_el.get("data-ga-item-name", "") or name_el.get_text(strip=True)
                    if not item_url:
                        href = name_el.get("href", "")
                        item_url = f"https://www.buyma.com{href}" if href.startswith("/") else href

                if not name:
                    skip_words = ["商品情報", "絞り込む", "除外する", "条件から外す", "タイムセール", "PERSONAL SHOPPER", "関税負担", "返品補償", "スピード配送", "送料込"]
                    text = card.get_text(separator="|", strip=True)
                    parts = [p.strip() for p in text.split("|") if p.strip()]
                    for part in parts:
                        if any(sw in part for sw in skip_words):
                            continue
                        if len(part) > 5 and "¥" not in part and "OFF" not in part and "カラー" not in part:
                            name = part
                            break

                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                if not item_url:
                    link = card.select_one("a[href*='/item/']")
                    if link:
                        href = link.get("href", "")
                        item_url = f"https://www.buyma.com{href}" if href.startswith("/") else href

                price = ""
                price_el = card.select_one(".pricetxt")
                if price_el:
                    price = price_el.get_text(strip=True)
                else:
                    text = card.get_text(separator="|", strip=True)
                    m = re.search(r'¥[\d,]+', text)
                    if m:
                        price = m.group()

                image = ""
                img_el = card.select_one("img[src*='buyma']")
                if img_el:
                    image = img_el.get("src", "")

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": item_url,
                })

        except Exception as e:
            print(f"[{label}] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[{label}] {len(items)} 件取得")
    return items


def _fetch_buyma_ranking(label, url, max_items=20):
    """BUYMA のランキングページ（/rank/）から人気アイテムを取得する共通関数"""
    print(f"[{label}] 人気アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(600)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select("li.bc-ranking__item")
            for card in cards:
                if len(items) >= max_items:
                    break

                text = card.get_text(separator="|", strip=True)
                parts = [p.strip() for p in text.split("|") if p.strip()]

                # 最初の数字（順位）をスキップして商品名を取得
                name = ""
                for part in parts:
                    if part.isdigit():
                        continue
                    if "¥" in part or "OFF" in part or "送料" in part:
                        break
                    if len(part) > 3:
                        name = part
                        break

                if not name:
                    continue

                # 価格
                price = ""
                m = re.search(r'¥[\d,]+', text)
                if m:
                    price = m.group()

                # URL
                item_url = ""
                link = card.select_one("a[href*='/item/']")
                if link:
                    href = link.get("href", "")
                    item_url = f"https://www.buyma.com{href}" if href.startswith("/") else href

                # 画像
                image = ""
                img_el = card.select_one("img[src*='buyma']")
                if img_el:
                    image = img_el.get("src", "")

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": item_url,
                })

        except Exception as e:
            print(f"[{label}] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[{label}] {len(items)} 件取得")
    return items


# ──────────────────────────────────────────────────────────
# SATUR (BUYMA)
# ──────────────────────────────────────────────────────────

def fetch_satur_buyma(max_items=20):
    return _fetch_buyma_brand(
        "SATUR (BUYMA)",
        "https://www.buyma.com/r/_SATUR-%E3%82%BB%E3%82%BF%E3%83%BC/",
        max_items,
    )


# ──────────────────────────────────────────────────────────
# AMI PARIS
# ──────────────────────────────────────────────────────────

def fetch_ami_paris(max_items=20):
    return _fetch_buyma_brand(
        "AMI PARIS (BUYMA)",
        "https://www.buyma.com/r/-C1002/amiparis/",
        max_items,
    )


def fetch_thug_club_buyma(max_items=20):
    return _fetch_buyma_brand(
        "Thug Club (BUYMA)",
        "https://www.buyma.com/r/Thug%20Club/",
        max_items,
    )


# ──────────────────────────────────────────────────────────
# Acne Studios
# ──────────────────────────────────────────────────────────

def fetch_acne_studios(max_items=20):
    print("[Acne Studios] メンズ新着アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto("https://www.acnestudios.com/jp/ja/man/new-arrivals/?sz=56", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select("div.product-tile")
            seen_names = set()
            for card in cards:
                if len(items) >= max_items:
                    break

                name_el = card.select_one(".product-tile__name")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                price_el = card.select_one(".product-tile__price")
                price = price_el.get_text(strip=True) if price_el else ""

                link = card.select_one("a.tile__link") or card.select_one("a[href]")
                url = link.get("href", "") if link else ""

                img_el = card.select_one("img[src*='acnestudios']")
                image = img_el.get("src", "") if img_el else ""

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })

        except Exception as e:
            print(f"[Acne Studios] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[Acne Studios] {len(items)} 件取得")
    return items


def fetch_acne_studios_buyma(max_items=20):
    return _fetch_buyma_ranking(
        "Acne Studios (BUYMA)",
        "https://www.buyma.com/rank/_ACNE-JEANS-%E3%82%A2%E3%82%AF%E3%83%8D%E3%82%B8%E3%83%BC%E3%83%B3%E3%82%BA/",
        max_items,
    )


# ──────────────────────────────────────────────────────────
# Stüssy
# ──────────────────────────────────────────────────────────

def fetch_stussy(max_items=20):
    print("[Stüssy] 新着アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto("https://jp.stussy.com/collections/new-arrivals", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            title_links = soup.select("a.product-card__title-link")
            seen_names = set()
            for tl in title_links:
                if len(items) >= max_items:
                    break

                name = tl.get_text(strip=True)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                href = tl.get("href", "")
                url = f"https://jp.stussy.com{href}" if href.startswith("/") else href

                parent = tl.find_parent("div", class_=lambda c: c and "product-card" in " ".join(c)) or tl.find_parent("li") or tl.find_parent("div")

                price = ""
                if parent:
                    for el in parent.select("[class*='price']"):
                        t = el.get_text(strip=True)
                        if "¥" in t:
                            m = re.search(r'¥[\d,]+', t)
                            if m:
                                price = m.group()
                                break

                image = ""
                if parent:
                    img_el = parent.select_one("img[src*='stussy'], img[src*='cdn']")
                    if img_el:
                        src = img_el.get("src", "")
                        image = f"https:{src}" if src.startswith("//") else src

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })

        except Exception as e:
            print(f"[Stüssy] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[Stüssy] {len(items)} 件取得")
    return items



# ──────────────────────────────────────────────────────────
# Supreme 公式
# ──────────────────────────────────────────────────────────

def fetch_supreme(max_items=20):
    print("[Supreme] 新着アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto("https://jp.supreme.com/collections/new", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            links = soup.select("a[href*='/products/']")
            seen_names = set()
            for el in links:
                if len(items) >= max_items:
                    break

                text = el.get_text(separator="|", strip=True)
                parts = [p.strip() for p in text.split("|") if p.strip()]

                # 商品名: "new", "sold out" 以外の最初のテキスト
                name = ""
                for part in parts:
                    if part.lower() in ("new", "sold out"):
                        continue
                    if "¥" in part:
                        break
                    name = part
                    break

                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                href = el.get("href", "")
                url = f"https://jp.supreme.com{href}" if href.startswith("/") else href

                price = ""
                m = re.search(r'¥[\d,]+', text)
                if m:
                    price = m.group()

                image = ""
                img_el = el.select_one("img")
                if img_el:
                    src = img_el.get("src", "")
                    image = f"https:{src}" if src.startswith("//") else src

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })

        except Exception as e:
            print(f"[Supreme] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[Supreme] {len(items)} 件取得")
    return items


# ──────────────────────────────────────────────────────────
# SNKRDUNK ブランド検索（汎用）
# ──────────────────────────────────────────────────────────

def _fetch_snkrdunk_brand(label, url, max_items=20):
    print(f"[{label}] 人気アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select("a[class*='productTile']")
            seen_names = set()
            for card in cards:
                if len(items) >= max_items:
                    break

                name_el = card.select_one("span[class*='productName']")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                href = card.get("href", "")
                item_url = href if href.startswith("http") else f"https://snkrdunk.com{href}"

                price = ""
                text = card.get_text(separator="|", strip=True)
                m = re.search(r'¥\|?([\d,]+)', text)
                if m:
                    price = f"¥{m.group(1)}"

                image = ""
                img_el = card.select_one("img")
                if img_el:
                    image = img_el.get("src", "") or img_el.get("data-src", "")

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": item_url,
                })

        except Exception as e:
            print(f"[{label}] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[{label}] {len(items)} 件取得")
    return items


def fetch_supreme_snkrdunk(max_items=20):
    return _fetch_snkrdunk_brand(
        "Supreme (SNKRDUNK)",
        "https://snkrdunk.com/search?brandIds=supreme",
        max_items,
    )


def fetch_stussy_snkrdunk(max_items=20):
    return _fetch_snkrdunk_brand(
        "Stüssy (SNKRDUNK)",
        "https://snkrdunk.com/search?brandIds=stussy&searchCategoryIds=2&keywords=Stussy+%E3%82%A2%E3%83%91%E3%83%AC%E3%83%AB&sort=popular",
        max_items,
    )


# ──────────────────────────────────────────────────────────
# HUMAN MADE 公式
# ──────────────────────────────────────────────────────────

def fetch_humanmade(max_items=20):
    print("[HUMAN MADE] 新着アイテム取得中...")
    items = []

    from playwright.sync_api import sync_playwright
    import re

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto("https://www.humanmade.jp/new-arrivals/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 600)")
                page.wait_for_timeout(500)

            soup = BeautifulSoup(page.content(), "html.parser")

            cards = soup.select(".product-tile-wrapper")
            seen_names = set()
            for card in cards:
                if len(items) >= max_items:
                    break

                # 商品名（imgのalt or リンクテキスト）
                img_el = card.select_one("img")
                name = img_el.get("alt", "").strip() if img_el else ""
                if not name:
                    link = card.select_one("a[href]")
                    name = link.get_text(strip=True) if link else ""
                if not name or name in seen_names:
                    continue
                seen_names.add(name)

                # URL
                link = card.select_one("a[href]")
                href = link.get("href", "") if link else ""
                url = f"https://www.humanmade.jp{href}" if href.startswith("/") else href

                # 価格
                price = ""
                text = card.get_text(separator="|", strip=True)
                m = re.search(r'¥[\d,]+', text)
                if m:
                    price = m.group()

                # 画像
                image = ""
                if img_el:
                    src = img_el.get("src", "") or img_el.get("data-src", "")
                    if src.startswith("//"):
                        src = "https:" + src
                    image = src

                items.append({
                    "rank": len(items) + 1,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })

        except Exception as e:
            print(f"[HUMAN MADE] 取得失敗: {e}")
        finally:
            browser.close()

    print(f"[HUMAN MADE] {len(items)} 件取得")
    return items


def fetch_humanmade_snkrdunk(max_items=20):
    return _fetch_snkrdunk_brand(
        "HUMAN MADE (SNKRDUNK)",
        "https://snkrdunk.com/search?brandIds=humanmade&searchCategoryIds=2&keywords=HUMAN+MADE+%E3%82%A2%E3%83%91%E3%83%AC%E3%83%AB&sort=popular",
        max_items,
    )


# 保存 (JSON + HTML)
# ──────────────────────────────────────────────────────────

def save_json(brand_results, BRANDS):
    ensure_output_dir()

    result = {
        "date": TODAY,
        "fetched_at": datetime.now().isoformat(),
        "brands": {},
    }
    for key, items in brand_results.items():
        conf = BRANDS[key]
        result["brands"][key] = {
            "name": conf["name"],
            "source": conf["url"],
            "count": len(items),
            "items": items,
        }

    filepath = os.path.join(OUTPUT_DIR, f"brand_ranking_{TODAY}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"JSON 保存完了: {filepath}")
    return filepath


def save_html(brand_results, BRANDS):
    ensure_output_dir()

    def render_items(items, show_brand=False):
        if not items:
            return '<p class="empty">取得できませんでした</p>'
        rows = []
        for item in items:
            img_src = item.get("image", "")
            url = item.get("url", "")
            img_inner = f'<img src="{img_src}" alt="" loading="lazy">' if img_src else '<div class="no-img">NO IMAGE</div>'
            img_tag = f'<a href="{url}" target="_blank" rel="noreferrer">{img_inner}</a>' if url and img_src else img_inner
            name = item.get("name", "")
            brand = item.get("brand", "")
            price = item.get("price", "")
            rank = item.get("rank", "?")

            name_html = f'<a href="{url}" target="_blank" rel="noreferrer">{name}</a>' if url else name
            brand_html = f'<span class="brand">{brand}</span>' if brand and show_brand else ""
            price_html = f'<span class="price">{price}</span>' if price else ""

            rows.append(f'''
            <div class="item">
              <span class="rank">#{rank}</span>
              <div class="img-wrap">{img_tag}</div>
              <div class="info">
                <div class="name">{name_html}</div>
                {brand_html}
                {price_html}
              </div>
            </div>''')
        return "\n".join(rows)

    # 目次
    toc_items = "\n".join(
        f'    <li><a href="#{key}">{conf["name"]}</a></li>'
        for key, conf in BRANDS.items()
    )

    # セクション
    sections = ""
    for key, items in brand_results.items():
        conf = BRANDS[key]
        sections += f'''
<div class="section" id="{key}">
  <h2>{conf["name"]} <span class="badge" style="background:{conf["badge_color"]}">{conf["badge_label"]}</span> <span class="count">{len(items)} items</span></h2>
  <div class="items">
    {render_items(items, show_brand=True)}
  </div>
  <a href="{conf["view_all"]}" target="_blank" rel="noreferrer" class="btn-all">{conf["name"]} を全部見る</a>
</div>
'''

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ブランド新着情報&人気ランキング {TODAY}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 20px; padding-top: 60px; }}
  h1 {{ text-align: center; margin-bottom: 8px; font-size: 1.8em; }}
  .date {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 0.95em; }}
  .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .section h2 {{ font-size: 1.3em; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #eee; }}
  .section h2 .badge {{ font-size: 0.65em; padding: 3px 8px; border-radius: 4px; color: #fff; vertical-align: middle; margin-left: 8px; }}
  .items {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }}
  @media (max-width: 600px) {{
    .items {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }}
  }}
  .item {{ background: #fafafa; border-radius: 8px; overflow: hidden; transition: transform 0.15s; border: 1px solid #eee; }}
  .item:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
  .rank {{ position: absolute; top: 6px; left: 6px; background: rgba(0,0,0,0.75); color: #fff; font-weight: 700; font-size: 0.85em; padding: 2px 8px; border-radius: 4px; z-index: 1; }}
  .img-wrap {{ position: relative; width: 100%; aspect-ratio: 1; background: #eee; overflow: hidden; }}
  .img-wrap img {{ width: 100%; height: 100%; object-fit: cover; }}
  .no-img {{ width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #bbb; font-size: 0.8em; }}
  .info {{ padding: 10px; }}
  .name {{ font-size: 0.85em; line-height: 1.4; margin-bottom: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
  .name a {{ color: #333; text-decoration: none; }}
  .name a:hover {{ text-decoration: underline; }}
  .brand {{ display: block; font-size: 0.75em; color: #888; margin-bottom: 4px; }}
  .price {{ display: block; font-size: 0.9em; font-weight: 600; color: #e44; }}
  .empty {{ color: #aaa; text-align: center; padding: 40px; }}
  .count {{ font-size: 0.8em; color: #999; font-weight: normal; }}
  nav.toc {{ position: fixed; top: 0; left: 0; right: 0; z-index: 9999; background: #ffffff; margin: 0; padding: 0; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }}
  nav.toc ul {{ list-style: none; display: flex; flex-wrap: wrap; gap: 0; margin: 0; padding: 0; justify-content: center; }}
  nav.toc li {{ flex-shrink: 0; }}
  nav.toc li a {{ display: block; padding: 10px 14px; color: #555; text-decoration: none; font-size: 12px; font-weight: 600; white-space: nowrap; border-bottom: 2px solid transparent; transition: all 0.2s; }}
  nav.toc li a:hover, nav.toc li a.active {{ color: #000; border-bottom-color: #000; }}
  @media (max-width: 600px) {{
    body {{ padding-top: 80px; }}
    nav.toc ul {{ justify-content: flex-start; }}
    nav.toc li a {{ padding: 8px 11px; font-size: 11px; }}
    .section {{ scroll-margin-top: 80px; }}
  }}
  .section {{ scroll-margin-top: 52px; }}
  .btn-all {{ display: block; margin: 16px auto 0; padding: 10px 24px; background: #333; color: #fff; border: none; border-radius: 8px; font-size: 0.85em; font-weight: 600; text-decoration: none; text-align: center; width: fit-content; transition: background 0.2s; }}
  .btn-all:hover {{ background: #555; }}
</style>
</head>
<body>
<nav class="toc">
  <ul>
{toc_items}
  </ul>
</nav>
<h1>ブランド新着情報&人気ランキング</h1>
<p class="date">{TODAY}</p>
{sections}
<script>
(function(){{
  var links = document.querySelectorAll('.toc a');
  var sections = [];
  links.forEach(function(a){{
    var s = document.querySelector(a.getAttribute('href'));
    if(s) sections.push({{el:s, link:a}});
  }});
  function update(){{
    var scrollY = window.scrollY + 60;
    var current = sections[0];
    sections.forEach(function(s){{
      if(s.el.offsetTop <= scrollY) current = s;
    }});
    links.forEach(function(a){{ a.classList.remove('active'); }});
    if(current) {{
      current.link.classList.add('active');
      var nav = document.querySelector('.toc ul');
      var linkLeft = current.link.offsetLeft;
      var navWidth = nav.offsetWidth;
      nav.scrollTo({{left: linkLeft - navWidth/2 + current.link.offsetWidth/2, behavior:'smooth'}});
    }}
  }}
  window.addEventListener('scroll', update, {{passive:true}});
  update();
}})();
</script>
</body>
</html>'''

    filepath = os.path.join(OUTPUT_DIR, f"brand_ranking_{TODAY}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    # GitHub Pages 用
    docs_dir = os.path.join(os.path.dirname(OUTPUT_DIR), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    docs_path = os.path.join(docs_dir, "brands.html")
    with open(docs_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML 保存完了: {filepath}")
    return filepath


# ──────────────────────────────────────────────────────────
# Discord 投稿
# ──────────────────────────────────────────────────────────

def build_embed(brand_name, color, items, show_brand=False, badge_label="NEW"):
    if not items:
        return {
            "title": f"{brand_name} - 取得失敗",
            "description": "データを取得できませんでした。",
            "color": color,
        }

    lines = []
    for item in items[:10]:
        rank = item.get("rank", "?")
        name = item.get("name", "")[:50]
        brand = item.get("brand", "")
        price = item.get("price", "")
        url = item.get("url", "")

        name_part = f"[{name}]({url})" if url else name
        brand_part = f" `{brand}`" if brand and show_brand else ""
        price_part = f"  {price}" if price else ""

        lines.append(f"**{rank}.** {name_part}{brand_part}{price_part}")

    if len(items) > 10:
        lines.append(f"_... 他 {len(items) - 10} 件_")

    thumbnail = {}
    if items[0].get("image"):
        thumbnail = {"url": items[0]["image"]}

    return {
        "title": f"{brand_name} {'人気アイテム' if badge_label == 'POPULAR' else '新着アイテム'} TOP {min(len(items), 10)}",
        "description": "\n".join(lines),
        "color": color,
        "thumbnail": thumbnail,
    }


def post_to_discord(brand_results, BRANDS):
    import random

    print("[Discord] ブランドランキングを投稿中...")

    # データがあるブランドのみ対象
    active_keys = [k for k, items in brand_results.items() if items and k in BRANDS]

    # ランダムで3ブランドをピックアップ
    picked = random.sample(active_keys, min(3, len(active_keys)))
    rest = [k for k in active_keys if k not in picked]

    # ヘッダー
    header_payload = {
        "content": f"## ブランド新着情報&人気ランキング - {TODAY}",
    }
    resp = requests.post(BRAND_WEBHOOK_URL, json=header_payload, timeout=15)
    if resp.status_code in (200, 204):
        print("[Discord] ヘッダー投稿成功")

    # ピックアップ3ブランドの Embed を投稿
    embeds = []
    for key in picked:
        conf = BRANDS[key]
        color = int(conf["badge_color"].lstrip("#"), 16)
        embeds.append(build_embed(conf["name"], color, brand_results[key], show_brand=True, badge_label=conf.get("badge_label", "NEW")))

    if embeds:
        time.sleep(0.5)
        requests.post(BRAND_WEBHOOK_URL, json={"embeds": embeds}, timeout=15)

    # 残りのブランド + 全ブランド一覧を案内
    # 同一ベースブランドの派生（atmos, BUYMA, SNKRDUNK）をまとめて表示
    base_brands = []
    seen_bases = set()
    for k in BRANDS:
        base = k.split("_buyma")[0].split("_snkrdunk")[0].split("_atmos")[0]
        if base not in seen_bases:
            seen_bases.add(base)
            base_brands.append(BRANDS[k]["name"].split(" (")[0])

    footer_lines = []

    if rest:
        rest_names = "、".join(BRANDS[k]["name"] for k in rest)
        footer_lines.append(f"**⚡️ その他のブランド更新**\n{rest_names}")

    footer_lines.append(f"\n**📋 監視中の全ブランド（{len(base_brands)}件）**\n{' / '.join(base_brands)}")
    footer_lines.append(f"\n全ブランドの詳細はこちら 👉 {PAGES_URL}")

    time.sleep(0.5)
    requests.post(BRAND_WEBHOOK_URL, json={"content": "\n".join(footer_lines)}, timeout=15)

    print(f"[Discord] 投稿完了（ピックアップ: {', '.join(BRANDS[k]['name'] for k in picked)}）")


# ──────────────────────────────────────────────────────────
# コンソール表示
# ──────────────────────────────────────────────────────────

def print_summary(brand_name, items):
    print(f"\n{'─' * 60}")
    print(f"  {brand_name} TOP {min(len(items), 10)}")
    print(f"{'─' * 60}")
    if not items:
        print("  (取得できませんでした)")
        return
    for item in items[:10]:
        rank = item.get("rank", "?")
        name = item.get("name", "")[:45]
        price = item.get("price", "")
        has_img = "img" if item.get("image") else "   "
        line = f"  {rank:>2}. [{has_img}] {name}"
        if price:
            line += f"  {price}"
        print(line)
    if len(items) > 10:
        print(f"  ... 他 {len(items) - 10} 件")


# ──────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────

# フェッチャー名 → 関数のマッピング
FETCHERS = {
    "fetch_adidas": fetch_adidas,
    "fetch_adidas_atmos": fetch_adidas_atmos,
    "fetch_carhartt": fetch_carhartt,
    "fetch_diesel": fetch_diesel,
    "fetch_satur": fetch_satur,
    "fetch_satur_buyma": fetch_satur_buyma,
    "fetch_ami_paris": fetch_ami_paris,
    "fetch_thug_club_buyma": fetch_thug_club_buyma,
    "fetch_acne_studios": fetch_acne_studios,
    "fetch_stussy": fetch_stussy,
    "fetch_supreme_snkrdunk": fetch_supreme_snkrdunk,
    "fetch_supreme": fetch_supreme,
    "fetch_stussy_snkrdunk": fetch_stussy_snkrdunk,
    "fetch_acne_studios_buyma": fetch_acne_studios_buyma,
    "fetch_humanmade": fetch_humanmade,
    "fetch_humanmade_snkrdunk": fetch_humanmade_snkrdunk,
}


def main():
    print(f"=== ブランド新着情報&人気ランキング Bot ({TODAY}) ===\n")

    BRANDS = load_brands()

    brand_results = {}
    for key, conf in BRANDS.items():
        fetcher_name = conf["fetcher"]
        fetcher = FETCHERS.get(fetcher_name)
        if not fetcher:
            print(f"[{conf['name']}] フェッチャーが見つかりません: {fetcher_name}")
            brand_results[key] = []
            continue
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                brand_results[key] = fetcher()
            except Exception as e:
                print(f"[{conf['name']}] 致命的エラー: {e}")
                brand_results[key] = []
            if brand_results[key]:
                break
            if attempt < max_retries:
                print(f"[{conf['name']}] 0件のためリトライ ({attempt}/{max_retries})...")
                time.sleep(3)

    # 結果表示
    for key, items in brand_results.items():
        print_summary(BRANDS[key]["name"], items)

    # 保存
    json_path = save_json(brand_results, BRANDS)
    html_path = save_html(brand_results, BRANDS)

    total = sum(len(items) for items in brand_results.values())
    print(f"\n合計 {total} 件のブランドデータを取得しました。")

    # GitHub Pages に push
    if not IS_CI:
        import subprocess
        try:
            subprocess.run(["git", "add", "docs/", "data/"], cwd=REPO_DIR, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Update brand ranking {TODAY}"], cwd=REPO_DIR, check=True, capture_output=True)
            subprocess.run(["git", "push"], cwd=REPO_DIR, check=True, capture_output=True)
            print(f"GitHub Pages 更新完了: {PAGES_URL}")
        except subprocess.CalledProcessError as e:
            print(f"[GitHub] push 失敗: {e.stderr.decode()[:200] if e.stderr else e}")

    # Discord に投稿
    post_to_discord(brand_results, BRANDS)

    print(f"HTML で確認: open {html_path}")
    return json_path, html_path


if __name__ == "__main__":
    main()
