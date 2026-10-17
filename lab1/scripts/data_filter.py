#!/usr/bin/env python3
import os
import csv
from bs4 import BeautifulSoup

IN_FILE = "data/raw_data/web_data.html"
MARKET_CSV = "data/processed_data/market_data.csv"
NEWS_CSV = "data/processed_data/news_data.csv"

os.makedirs("data/processed_data", exist_ok=True)

print("Filtering fields...")

with open(IN_FILE, "r", encoding="utf-8", errors="ignore") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

market = []
for card in soup.select("a.MarketCard-container"):
    sym = card.select_one("span.MarketCard-symbol")
    pos = card.select_one("span.MarketCard-stockPosition")
    pct = (card.select_one("span.MarketCard-changesPct")
           or card.select_one("span.MarketCard-changePct"))

    market.append([
        sym.get_text(strip=True) if sym else "",
        pos.get_text(strip=True) if pos else "",
        pct.get_text(strip=True) if pct else "",
    ])

print("Storing Market data...")
with open(MARKET_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["marketCard_symbol", "marketCard_stockPosition", "marketCardchangePct"])
    w.writerows(market)
print(f"CSV created: {MARKET_CSV} (rows={len(market)})")

news = []
for item in soup.select("ul.LatestNews-list > li.LatestNews-item"):
    t = item.select_one("time.LatestNews-timestamp")
    a = item.select_one("a.LatestNews-headline")

    ts = t.get_text(strip=True) if t else ""
    title = a.get_text(strip=True) if a else ""
    link = (a.get("href") or "").strip() if a else ""

    news.append([ts, title, link])

print("Storing News data...")
with open(NEWS_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["LatestNews_timestamp", "title", "link"])
    w.writerows(news)
print(f"CSV created: {NEWS_CSV} (rows={len(news)})")

print("Done.")
