from playwright.sync_api import sync_playwright
import re
RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/[a-z0-9\-]+\.html")
URL = "https://www.cnbc.com/site-map/articles/2024/August/15/"
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    pg.goto(URL, wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(3000)
    hrefs = pg.eval_on_selector_all("a", "els => els.map(e => [e.href, e.innerText])")
    b.close()
hit = [(h, t) for h, t in hrefs if RE.search(h) and "/2024/08/15/" in h]
print(f"Total link di halaman : {len(hrefs)}")
print(f"Link artikel 15 Agu 24: {len(hit)}")
for h, t in hit[:5]:
    print(f"  {t[:65]}")
    print(f"    {h}")
print("\nBERHASIL -> lanjut bangun scraper Playwright" if hit else "\nMASIH KOSONG -> pindah sumber berita")
