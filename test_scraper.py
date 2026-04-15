import os, requests

key = os.environ.get("SCRAPER_API_KEY", "")
print(f"API Key length: {len(key)}")

# 1. 簡単なサイトでキーの有効性チェック
print("\n=== Test 1: httpbin (no render) ===")
r = requests.get("https://api.scraperapi.com", params={
    "api_key": key, "url": "https://httpbin.org/ip"
}, timeout=30)
print(f"Status: {r.status_code}, Body: {r.text[:200]}")

# 2. adidas.jp render=false
print("\n=== Test 2: adidas.jp (no render) ===")
r = requests.get("https://api.scraperapi.com", params={
    "api_key": key, "url": "https://www.adidas.jp/new_arrivals", "country_code": "jp"
}, timeout=60)
print(f"Status: {r.status_code}, Length: {len(r.text)}")
if r.status_code == 200:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    print(f"Title: {soup.title.string if soup.title else 'no title'}")

# 3. adidas.jp render=true
print("\n=== Test 3: adidas.jp (render=true) ===")
r = requests.get("https://api.scraperapi.com", params={
    "api_key": key, "url": "https://www.adidas.jp/new_arrivals",
    "country_code": "jp", "render": "true"
}, timeout=120)
print(f"Status: {r.status_code}, Length: {len(r.text)}")
if r.status_code == 200:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    print(f"Title: {soup.title.string if soup.title else 'no title'}")
    cards = soup.select("article[class*='product-card']")
    print(f"Cards: {len(cards)}")

# 4. atmos render=true
print("\n=== Test 4: atmos (render=true) ===")
r = requests.get("https://api.scraperapi.com", params={
    "api_key": key, "url": "https://www.atmos-tokyo.com/category/all?brand=adidas",
    "country_code": "jp", "render": "true"
}, timeout=120)
print(f"Status: {r.status_code}, Length: {len(r.text)}")
if r.status_code == 200:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    print(f"Title: {soup.title.string if soup.title else 'no title'}")
    cards = soup.select("li.lists-products-item")
    print(f"Cards: {len(cards)}")
