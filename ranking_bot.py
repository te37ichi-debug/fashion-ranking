#!/usr/bin/env python3
"""
Fashion Ranking Bot
ZARA・MUSINSA・スニーカーダンク・ZOZOTOWN の人気ランキングを取得・保存するスクリプト

- ZARA: 公式サイト内部 API (undetected-chromedriver)
- MUSINSA: 日本サイト (global.musinsa.com/jp)
- スニーカーダンク: 人気スニーカー + ストリートウェア
- ZOZOTOWN: undetected-chromedriver で Akamai WAF 回避
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
PAGES_URL = "https://te37ichi-debug.github.io/fashion-ranking/"
IS_CI = os.environ.get("CI") == "true"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─── ZOZOTOWN (undetected-chromedriver) ────────────────────

def fetch_zozotown(max_items=20):
    print("[ZOZOTOWN] undetected-chromedriver でランキングページにアクセス中...")
    items = []

    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = uc.ChromeOptions()
    options.add_argument("--lang=ja-JP")
    options.add_argument("--window-size=1280,720")

    driver = uc.Chrome(options=options, headless=IS_CI, version_main=None if IS_CI else 146)

    try:
        driver.get("https://zozo.jp/ranking/all-sales-men.html")
        time.sleep(6)

        # ページがブロックされていないか確認
        if "Access Denied" in driver.page_source:
            print("[ZOZOTOWN] Akamai WAF によりブロックされました")
            return items

        # スクロールして商品を読み込む
        for _ in range(8):
            driver.execute_script("window.scrollBy(0, 600)")
            time.sleep(0.6)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # .catalog-item が ZOZOTOWN ランキングの商品要素
        product_elements = soup.select("li.catalog-item")
        if product_elements:
            print(f"[ZOZOTOWN] {len(product_elements)} 件の商品を検出")

        for i, el in enumerate(product_elements[:max_items], 1):
            name_el = el.select_one(".catalog-property")
            brand_el = el.select_one(".catalog-header-h")
            price_el = el.select_one(".catalog-price-number")
            img_el = el.select_one("img.catalog-img")
            link_el = el.select_one("a.catalog-link")

            name = name_el.get_text(strip=True) if name_el else ""
            brand = brand_el.get_text(strip=True) if brand_el else ""
            price = f"¥{price_el.get_text(strip=True)}" if price_el else ""
            image = img_el.get("src", "") if img_el else ""
            url = ""
            if link_el:
                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"https://zozo.jp{href}" if href else ""

            if name:
                items.append({"rank": i, "name": name, "brand": brand, "price": price, "image": image, "url": url})

    except Exception as e:
        print(f"[ZOZOTOWN] エラー: {e}")
    finally:
        driver.quit()

    print(f"[ZOZOTOWN] {len(items)} 件取得")
    return items


# ─── ZARA (公式サイト API / undetected-chromedriver) ───────

# ZARA メンズ デイリーランキング カテゴリ ID
ZARA_MEN_DAILY_RANKING_ID = 2541435

def fetch_zara(max_items=20):
    print("[ZARA] 公式サイト API からメンズランキング取得中...")
    items = []

    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    options.add_argument("--lang=ja-JP")
    options.add_argument("--window-size=1280,720")

    driver = uc.Chrome(options=options, headless=IS_CI, version_main=None if IS_CI else 146)

    try:
        driver.get("https://www.zara.com/jp/")
        time.sleep(6)

        # ブラウザ内 JS でカテゴリ API を呼び出し
        result = driver.execute_script(f"""
            const resp = await fetch('/jp/ja/category/{ZARA_MEN_DAILY_RANKING_ID}/products?ajax=true');
            if (!resp.ok) return null;
            return await resp.json();
        """)

        if not result:
            print("[ZARA] API レスポンスなし")
            return items

        groups = result.get("productGroups", [])
        if not groups:
            print("[ZARA] productGroups が空")
            return items

        rank = 1
        for element in groups[0].get("elements", []):
            for comp in element.get("commercialComponents", []):
                if rank > max_items:
                    break

                name = comp.get("name", "")
                if not name:
                    continue

                # 価格（整数、例: 8590 → ¥8,590）
                price_val = comp.get("price")
                price = f"¥{price_val:,}" if isinstance(price_val, int) else ""

                # 画像 URL
                image = ""
                detail = comp.get("detail", {})
                colors = detail.get("colors", [])
                if colors:
                    xmedia = colors[0].get("xmedia", [])
                    if xmedia:
                        img_url = xmedia[0].get("url", "")
                        image = img_url.replace("{width}", "563") if img_url else ""

                # 商品 URL（reference 番号ベース: 確実に商品ページへリダイレクトされる）
                reference = comp.get("reference", "")
                ref_num = reference.split("-")[0] if reference else ""
                url = f"https://www.zara.com/jp/ja/-p{ref_num}.html" if ref_num else ""

                items.append({
                    "rank": rank,
                    "name": name,
                    "price": price,
                    "image": image,
                    "url": url,
                })
                rank += 1

            if rank > max_items:
                break

    except Exception as e:
        print(f"[ZARA] エラー: {e}")
    finally:
        driver.quit()

    print(f"[ZARA] {len(items)} 件取得")
    return items


# ─── MUSINSA Japan (global.musinsa.com) ───────────────────

def fetch_musinsa(max_items=20):
    print("[MUSINSA] 日本サイトからランキング取得中...")

    headers = {
        "User-Agent": UA,
        "Accept": "text/html",
        "Accept-Language": "ja",
    }

    items = []
    try:
        resp = requests.get("https://global.musinsa.com/jp/main", headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text

        # RANKING_GOODS_CATEGORY セクションの goodsList を抽出
        ranking_idx = text.find('"RANKING_GOODS_CATEGORY"')
        if ranking_idx < 0:
            print("[MUSINSA] ランキングセクションが見つかりません")
            return items

        gl_idx = text.find('"goodsList":[', ranking_idx)
        if gl_idx < 0:
            print("[MUSINSA] goodsList が見つかりません")
            return items

        # JSON 配列を抽出
        arr_start = text.find('[', gl_idx)
        depth = 0
        arr_end = arr_start
        for i in range(arr_start, min(arr_start + 50000, len(text))):
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
            if depth == 0:
                arr_end = i + 1
                break

        import json as _json
        goods = _json.loads(text[arr_start:arr_end])

        for rank, g in enumerate(goods[:max_items], 1):
            name = g.get("goodsName", "")
            if not name:
                continue

            price_val = g.get("price")
            currency = g.get("currency", "¥")
            price = f"{currency}{price_val:,}" if price_val else ""

            image_url = g.get("imageUrl", "")
            if image_url.startswith("//"):
                image_url = "https:" + image_url

            landing = g.get("landingUrl", "")
            url = f"https://global.musinsa.com{landing}" if landing else ""

            items.append({
                "rank": rank,
                "name": name,
                "brand": g.get("brandName", ""),
                "price": price,
                "image": image_url,
                "url": url,
            })

    except Exception as e:
        print(f"[MUSINSA] 取得失敗: {e}")

    print(f"[MUSINSA] {len(items)} 件取得")
    return items


# ─── スニーカーダンク (snkrdunk.com) ──────────────────────

def _parse_snkrdunk_items(soup, link_prefix, max_items=20):
    """snkrdunk の item-block 要素をパース"""
    items = []
    products = soup.select(f"a.item-block[href*='/{link_prefix}/']")
    if not products:
        products = soup.select("a.item-block")

    for el in products[:max_items]:
        name_el = el.select_one("p.item-name")
        price_el = el.select_one("p.item-price")
        img_el = el.select_one("img")

        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        price_text = price_el.get_text(strip=True) if price_el else ""
        # "¥12,878〜即購入可" → "¥12,878〜"
        price = price_text.split("即")[0].strip() if "即" in price_text else price_text.split("出品")[0].strip()

        image = img_el.get("data-src", "") or img_el.get("src", "") if img_el else ""
        if "loading.png" in image:
            image = img_el.get("data-src", "") if img_el else ""

        href = el.get("href", "")
        url = f"https://snkrdunk.com{href}" if href.startswith("/") else href

        items.append({
            "rank": len(items) + 1,
            "name": name,
            "price": price,
            "image": image,
            "url": url,
        })

    return items


def fetch_snkrdunk_sneakers(max_items=20):
    print("[スニーカーダンク] 人気スニーカー取得中...")
    items = []

    try:
        resp = requests.get(
            "https://snkrdunk.com/products?type=hottest",
            headers={"User-Agent": UA, "Accept": "text/html"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = _parse_snkrdunk_items(soup, "products", max_items)
    except Exception as e:
        print(f"[スニーカーダンク] スニーカー取得失敗: {e}")

    print(f"[スニーカーダンク] スニーカー {len(items)} 件取得")
    return items


def fetch_snkrdunk_apparel(max_items=20):
    print("[スニーカーダンク] 人気ストリートウェア取得中...")
    items = []

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=None if IS_CI else "chrome")
        page = browser.new_page(user_agent=UA)

        try:
            page.goto("https://snkrdunk.com/apparels?type=hottest&department=apparel", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(600)

            soup = BeautifulSoup(page.content(), "html.parser")
            items = _parse_snkrdunk_items(soup, "apparels", max_items)
        except Exception as e:
            print(f"[スニーカーダンク] ストリートウェア取得失敗: {e}")
        finally:
            browser.close()

    print(f"[スニーカーダンク] ストリートウェア {len(items)} 件取得")
    return items


# ─── 保存 (JSON + HTML) ───────────────────────────────────

def save_json(zara, musinsa, snkr_sneakers, snkr_apparel, zozotown):
    ensure_output_dir()

    result = {
        "date": TODAY,
        "fetched_at": datetime.now().isoformat(),
        "zara": {
            "source": "zara.com (official API)",
            "count": len(zara),
            "items": zara,
        },
        "musinsa": {
            "source": "global.musinsa.com/jp",
            "count": len(musinsa),
            "items": musinsa,
        },
        "snkrdunk_sneakers": {
            "source": "snkrdunk.com",
            "count": len(snkr_sneakers),
            "items": snkr_sneakers,
        },
        "snkrdunk_apparel": {
            "source": "snkrdunk.com",
            "count": len(snkr_apparel),
            "items": snkr_apparel,
        },
        "zozotown": {
            "source": "zozo.jp (undetected-chromedriver)" if zozotown else "取得失敗",
            "count": len(zozotown),
            "items": zozotown,
        },
    }

    filepath = os.path.join(OUTPUT_DIR, f"ranking_{TODAY}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"JSON 保存完了: {filepath}")
    return filepath


def save_html(zara, musinsa, snkr_sneakers, snkr_apparel, zozotown):
    ensure_output_dir()

    def render_items(items, show_brand=False):
        if not items:
            return '<p class="empty">取得できませんでした</p>'
        rows = []
        for item in items:
            img_src = item.get("image", "")
            url = item.get("url", "")
            img_inner = f'<img src="{img_src}" alt="" loading="lazy">' if img_src else '<div class="no-img">NO IMAGE</div>'
            img_tag = f'<a href="{url}" target="_blank">{img_inner}</a>' if url and img_src else img_inner
            name = item.get("name", "")
            brand = item.get("brand", "")
            price = item.get("price", "")
            rank = item.get("rank", "?")

            name_html = f'<a href="{url}" target="_blank">{name}</a>' if url else name
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

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Men's Fashion Ranking {TODAY}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 20px; }}
  h1 {{ text-align: center; margin-bottom: 8px; font-size: 1.8em; }}
  .date {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 0.95em; }}
  .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .section h2 {{ font-size: 1.3em; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #eee; }}
  .section h2 .badge {{ font-size: 0.65em; padding: 3px 8px; border-radius: 4px; color: #fff; vertical-align: middle; margin-left: 8px; }}
  .badge-zozo {{ background: #00a0e9; }}
  .badge-zara {{ background: #000; }}
  .badge-musinsa {{ background: #1a1a1a; }}
  .badge-snkrdunk {{ background: #ff5722; }}
  .items {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }}
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
</style>
</head>
<body>
<h1>Men's Fashion Ranking</h1>
<p class="date">{TODAY}</p>

<div class="section">
  <h2>ZARA <span class="badge badge-zara">JP</span> <span class="count">{len(zara)} items</span></h2>
  <div class="items">
    {render_items(zara, show_brand=False)}
  </div>
</div>

<div class="section">
  <h2>MUSINSA <span class="badge badge-musinsa">JP</span> <span class="count">{len(musinsa)} items</span></h2>
  <div class="items">
    {render_items(musinsa, show_brand=True)}
  </div>
</div>

<div class="section">
  <h2>SNKRDUNK 人気スニーカー <span class="badge badge-snkrdunk">JP</span> <span class="count">{len(snkr_sneakers)} items</span></h2>
  <div class="items">
    {render_items(snkr_sneakers, show_brand=False)}
  </div>
</div>

<div class="section">
  <h2>SNKRDUNK 人気ストリートウェア <span class="badge badge-snkrdunk">JP</span> <span class="count">{len(snkr_apparel)} items</span></h2>
  <div class="items">
    {render_items(snkr_apparel, show_brand=False)}
  </div>
</div>

<div class="section">
  <h2>ZOZOTOWN <span class="badge badge-zozo">JP</span> <span class="count">{len(zozotown)} items</span></h2>
  <div class="items">
    {render_items(zozotown, show_brand=True)}
  </div>
</div>

</body>
</html>'''

    filepath = os.path.join(OUTPUT_DIR, f"ranking_{TODAY}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    # GitHub Pages 用に docs/index.html にもコピー
    docs_dir = os.path.join(os.path.dirname(OUTPUT_DIR), "docs")
    os.makedirs(docs_dir, exist_ok=True)
    docs_path = os.path.join(docs_dir, "index.html")
    with open(docs_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML 保存完了: {filepath}")
    return filepath


def print_summary(site_name, items):
    print(f"\n{'─' * 60}")
    print(f"  {site_name} ランキング TOP {min(len(items), 10)}")
    print(f"{'─' * 60}")
    if not items:
        print("  (取得できませんでした)")
        return
    for item in items[:10]:
        rank = item.get("rank", "?")
        name = item.get("name", "")[:45]
        brand = item.get("brand", "")
        price = item.get("price", "")
        has_img = "img" if item.get("image") else "   "
        line = f"  {rank:>2}. [{has_img}] {name}"
        if brand:
            line += f"  [{brand}]"
        if price:
            line += f"  {price}"
        print(line)
    if len(items) > 10:
        print(f"  ... 他 {len(items) - 10} 件")


# ─── Discord Webhook 投稿 ──────────────────────────────────

CONFIG_PATH = os.path.join(os.path.expanduser("~"), "discord-news-bot", "data", "config.json")


def load_webhook_url():
    """環境変数 or discord-news-bot の config.json から Webhook URL を取得"""
    # 環境変数を優先（GitHub Actions 用）
    env_url = os.environ.get("RANKING_WEBHOOK_URL")
    if env_url:
        print("[Discord] 環境変数から Webhook URL を取得")
        return env_url

    # ローカル: config.json から読み込み
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        ranking = config.get("ranking", {})
        if not ranking.get("enabled"):
            print("[Discord] ランキング Bot は無効に設定されています")
            return None
        url = ranking.get("webhookUrl", "")
        if not url:
            print("[Discord] Webhook URL が未設定です")
            return None
        return url
    except FileNotFoundError:
        print(f"[Discord] 設定ファイルが見つかりません: {CONFIG_PATH}")
        return None


def build_embed(site_name, site_color, items, show_brand=False):
    """1サイト分の Discord Embed を構築（TOP10 + サムネイル）"""
    if not items:
        return {
            "title": f"{site_name} - 取得失敗",
            "description": "ランキングデータを取得できませんでした。",
            "color": site_color,
        }

    lines = []
    for item in items[:10]:
        rank = item.get("rank", "?")
        name = item.get("name", "")[:50]
        brand = item.get("brand", "")
        price = item.get("price", "")
        url = item.get("url", "")

        name_part = name
        brand_part = f" `{brand}`" if brand and show_brand else ""
        price_part = f"  {price}" if price else ""

        lines.append(f"**{rank}.** {name_part}{brand_part}{price_part}")

    if len(items) > 10:
        lines.append(f"_... 他 {len(items) - 10} 件_")

    # 1位の画像をサムネイルに
    thumbnail = {}
    if items[0].get("image"):
        thumbnail = {"url": items[0]["image"]}

    return {
        "title": f"{site_name} メンズランキング TOP {min(len(items), 10)}",
        "description": "\n".join(lines),
        "color": site_color,
        "thumbnail": thumbnail,
    }


def post_to_discord(webhook_url, zara, musinsa, snkr_sneakers, snkr_apparel, zozotown, html_path):
    """Discord Webhook にランキングを投稿"""
    print("[Discord] ランキングを投稿中...")

    embeds = [
        build_embed("ZARA", 0x000000, zara, show_brand=False),
        build_embed("MUSINSA", 0x1A1A1A, musinsa, show_brand=True),
        build_embed("SNKRDUNK スニーカー", 0xFF5722, snkr_sneakers, show_brand=False),
        build_embed("SNKRDUNK ストリートウェア", 0xFF5722, snkr_apparel, show_brand=False),
    ]

    # まとめリンクを一番上に投稿
    header_payload = {
        "content": f"## 👟 Men's Fashion Ranking - {TODAY}\nまとめはこちら👉 {PAGES_URL}",
    }
    resp = requests.post(webhook_url, json=header_payload, timeout=15)
    if resp.status_code in (200, 204):
        print("[Discord] ヘッダー投稿成功")
    else:
        print(f"[Discord] 投稿失敗: {resp.status_code} {resp.text[:200]}")

    # Embed を投稿（4件ずつ）
    time.sleep(0.5)
    requests.post(webhook_url, json={"embeds": embeds[:4]}, timeout=15)

    # ZOZOTOWN は別メッセージで
    time.sleep(0.5)
    requests.post(webhook_url, json={"embeds": [build_embed("ZOZOTOWN", 0x00A0E9, zozotown, show_brand=True)]}, timeout=15)

    # 各サイト TOP1 の画像を個別に大きく投稿
    for site_name, items, color in [
        ("ZARA", zara, 0x000000),
        ("MUSINSA", musinsa, 0x1A1A1A),
        ("SNKRDUNK", snkr_sneakers, 0xFF5722),
        ("ZOZOTOWN", zozotown, 0x00A0E9),
    ]:
        if not items:
            continue
        top = items[0]
        if not top.get("image"):
            continue

        image_embed = {
            "embeds": [{
                "title": f"{site_name} #1: {top.get('name', '')[:60]}",
                "image": {"url": top["image"]},
                "color": color,
                "footer": {"text": f"{top.get('brand', '')}  {top.get('price', '')}".strip()},
            }]
        }
        time.sleep(0.5)
        requests.post(webhook_url, json=image_embed, timeout=15)

    print("[Discord] 投稿完了")


# ─── メイン ─────────────────────────────────────────────────

def main():
    print(f"=== Men's Fashion Ranking Bot ({TODAY}) ===\n")

    # 1. MUSINSA Japan（requests のみ、高速）
    musinsa_items = fetch_musinsa()

    # 2. スニーカーダンク - スニーカー（requests のみ）
    snkr_sneakers = fetch_snkrdunk_sneakers()

    # 3. スニーカーダンク - ストリートウェア（Playwright）
    snkr_apparel = fetch_snkrdunk_apparel()

    # 4. ZOZOTOWN（undetected-chromedriver）
    zozotown_items = fetch_zozotown()

    # 5. ZARA（undetected-chromedriver）
    zara_items = fetch_zara()

    # 結果表示
    print_summary("ZARA", zara_items)
    print_summary("MUSINSA", musinsa_items)
    print_summary("SNKRDUNK スニーカー", snkr_sneakers)
    print_summary("SNKRDUNK ストリートウェア", snkr_apparel)
    print_summary("ZOZOTOWN", zozotown_items)

    # 保存
    json_path = save_json(zara_items, musinsa_items, snkr_sneakers, snkr_apparel, zozotown_items)
    html_path = save_html(zara_items, musinsa_items, snkr_sneakers, snkr_apparel, zozotown_items)

    total = len(zara_items) + len(musinsa_items) + len(snkr_sneakers) + len(snkr_apparel) + len(zozotown_items)
    print(f"\n合計 {total} 件のランキングデータを取得しました。")

    # GitHub Pages に push（ローカル実行時のみ。CI では workflow が push する）
    if not IS_CI:
        import subprocess
        try:
            subprocess.run(["git", "add", "docs/", "data/"], cwd=REPO_DIR, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Update ranking {TODAY}"], cwd=REPO_DIR, check=True, capture_output=True)
            subprocess.run(["git", "push"], cwd=REPO_DIR, check=True, capture_output=True)
            print(f"GitHub Pages 更新完了: {PAGES_URL}")
        except subprocess.CalledProcessError as e:
            print(f"[GitHub] push 失敗: {e.stderr.decode()[:200] if e.stderr else e}")

    # Discord に投稿
    webhook_url = load_webhook_url()
    if webhook_url:
        post_to_discord(webhook_url, zara_items, musinsa_items, snkr_sneakers, snkr_apparel, zozotown_items, html_path)
    else:
        print("[Discord] Webhook 未設定のため Discord 投稿をスキップ")

    print(f"HTML で確認: open {html_path}")
    return json_path, html_path


if __name__ == "__main__":
    main()
