import os
import re
import json
import requests
from bs4 import BeautifulSoup

URL = "https://www.cnbc.com/world/?region=world"
OUT = "data/raw_data/web_data.html"
SYMBOLS = [".DJI", ".SPX", ".IXIC", ".VIX"]

def get_page():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text

def get_quotes(symbols):
    joined = "|".join(symbols)
    api = f"https://quote.cnbc.com/quote-html-webservice/quote.htm?symbols={joined}&output=json"
    r = requests.get(api, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    txt = r.text.strip()

    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"(\{.*\})", txt, flags=re.DOTALL)
        return json.loads(m.group(1)) if m else {}

def build_market_html(quotes_json):
    soup = BeautifulSoup("", "html.parser")
    banner = soup.new_tag("div", **{"class": "MarketsBanner-marketData"})

    q = quotes_json.get("QuickQuoteResult", {}).get("QuickQuote", [])
    mp = {}
    if isinstance(q, list):
        for it in q:
            sym = str(it.get("symbol", "")).strip()
            mp[sym] = (it.get("last", ""), it.get("change_pct", ""))

    for sym in SYMBOLS:
        last, chg = mp.get(sym, ("", ""))
        a = soup.new_tag("a", **{"class": "MarketCard-container", "href": "#"})
        a.append(soup.new_tag("div", **{"class": "MarketCard-row"}))
        a.contents[-1].append(soup.new_tag("span", **{"class": "MarketCard-symbol"}))
        a.contents[-1].contents[-1].string = sym

        a.append(soup.new_tag("div", **{"class": "MarketCard-row"}))
        a.contents[-1].append(soup.new_tag("span", **{"class": "MarketCard-stockPosition"}))
        a.contents[-1].contents[-1].string = str(last)

        a.append(soup.new_tag("div", **{"class": "MarketCard-row"}))
        a.contents[-1].append(soup.new_tag("span", **{"class": "MarketCard-changePct"}))
        a.contents[-1].contents[-1].string = str(chg)

        banner.append(a)

    return banner

def main():
    os.makedirs("data/raw_data", exist_ok=True)
    print("Fetching:", URL)

    html = get_page()
    soup = BeautifulSoup(html, "html.parser")
    latest_news = soup.find("ul", class_="LatestNews-list")

    quotes = get_quotes(SYMBOLS)
    market = build_market_html(quotes)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(market.prettify() + "\n")
        if latest_news:
            f.write(latest_news.prettify() + "\n")

    print("Saved:", OUT)

if __name__ == "__main__":
    main()
