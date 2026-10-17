#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import requests
import pandas as pd
from bs4 import BeautifulSoup
import pdfplumber

LOCAL_CARDS_JSON = "card_informations.json"
HTML_NEWS_URL = "https://www.pokeguardian.com/"
PDF_RULE_URL = "https://media.pocketmonsters.net/pdf/play-pokemon-tournament-rules-handbook-en-2025-01-01.pdf"

DATA_DIR = "data"
RAW_DIR = os.path.join(DATA_DIR, "raw_data")
OUT_DIR = os.path.join(DATA_DIR, "processed_data")
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

CARDS_CSV = os.path.join(OUT_DIR, "tcg_cards_from_json.csv")
NEWS_TEXT = os.path.join(OUT_DIR, "tcg_news_page_text.txt")
NEWS_ITEMS_CSV = os.path.join(OUT_DIR, "tcg_news_items.csv")
PDF_TEXT = os.path.join(OUT_DIR, "tcg_rules_handbook_text.txt")
UNIFIED_JSONL = os.path.join(OUT_DIR, "unified_records.jsonl")


def http_get(url, stream=False, timeout=60):
    headers = {"User-Agent": "DSCI560-Lab2"}
    return requests.get(url, headers=headers, stream=stream, timeout=timeout)


def normalize_text(s):
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def safe_get(d, key, default=""):
    if type(d) == dict and key in d:
        return d[key]
    return default


def join_list(lst):
    if type(lst) != list:
        return ""
    out = ""
    i = 0
    while i < len(lst):
        if i == 0:
            out = str(lst[i])
        else:
            out = out + "|" + str(lst[i])
        i += 1
    return out


def write_jsonl(path, records):
    f = open(path, "w", encoding="utf-8")
    i = 0
    while i < len(records):
        f.write(json.dumps(records[i], ensure_ascii=False) + "\n")
        i += 1
    f.close()


def load_cards_json_to_csv():
    f = open(LOCAL_CARDS_JSON, "r", encoding="utf-8")
    data = json.load(f)
    f.close()

    rows = []
    i = 0
    while i < len(data):
        c = data[i]
        if type(c) != dict:
            i += 1
            continue

        row = {}
        row["id"] = safe_get(c, "id")
        row["name"] = safe_get(c, "name")
        row["hp"] = safe_get(c, "hp", "")
        row["rarity"] = safe_get(c, "rarity")
        row["artist"] = safe_get(c, "artist")
        row["set_id"] = safe_get(c, "set_id")

        row["subtypes"] = join_list(safe_get(c, "subtypes", []))
        row["types"] = join_list(safe_get(c, "types", []))
        row["nationalPokedexNumbers"] = join_list(safe_get(c, "nationalPokedexNumbers", []))

        attacks = safe_get(c, "attacks", [])
        row["num_attacks"] = 0

        row["attack1_name"] = ""
        row["attack1_cost"] = ""
        row["attack1_damage"] = ""
        row["attack1_text"] = ""

        row["attack2_name"] = ""
        row["attack2_cost"] = ""
        row["attack2_damage"] = ""
        row["attack2_text"] = ""

        if type(attacks) == list:
            row["num_attacks"] = len(attacks)

            if len(attacks) >= 1 and type(attacks[0]) == dict:
                a1 = attacks[0]
                row["attack1_name"] = safe_get(a1, "name")
                row["attack1_cost"] = join_list(safe_get(a1, "cost", []))
                row["attack1_damage"] = safe_get(a1, "damage")
                row["attack1_text"] = safe_get(a1, "text")

            if len(attacks) >= 2 and type(attacks[1]) == dict:
                a2 = attacks[1]
                row["attack2_name"] = safe_get(a2, "name")
                row["attack2_cost"] = join_list(safe_get(a2, "cost", []))
                row["attack2_damage"] = safe_get(a2, "damage")
                row["attack2_text"] = safe_get(a2, "text")

        weaknesses = safe_get(c, "weaknesses", [])
        row["weakness_type"] = ""
        row["weakness_value"] = ""
        if type(weaknesses) == list and len(weaknesses) >= 1 and type(weaknesses[0]) == dict:
            w = weaknesses[0]
            row["weakness_type"] = safe_get(w, "type")
            row["weakness_value"] = safe_get(w, "value")

        rows.append(row)
        i += 1

    df = pd.DataFrame(rows)
    df.to_csv(CARDS_CSV, index=False, encoding="utf-8")

    # basic exploration (minimal prints)
    print("cards:", df.shape, "saved ->", CARDS_CSV)
    return df


def scrape_news():
    r = http_get(HTML_NEWS_URL, timeout=60)
    html = r.text

    raw_path = os.path.join(RAW_DIR, "news_page.html")
    f = open(raw_path, "w", encoding="utf-8")
    f.write(html)
    f.close()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    page_text = normalize_text(soup.get_text("\n", strip=True))

    f = open(NEWS_TEXT, "w", encoding="utf-8")
    f.write(page_text + "\n")
    f.close()

    items = []
    seen = set()
    links = soup.select("h2 a, h3 a")

    k = 0
    while k < len(links) and len(items) < 15:
        a = links[k]
        title = a.get_text(" ", strip=True)

        href = ""
        if "href" in a.attrs:
            href = a.attrs["href"]

        if title != "" and href != "":
            if href.startswith("/"):
                href = "https://www.pokeguardian.com" + href
            if "pokeguardian.com" in href and href not in seen:
                seen.add(href)
                items.append({"title": title, "url": href})
        k += 1

    pd.DataFrame(items).to_csv(NEWS_ITEMS_CSV, index=False, encoding="utf-8")
    print("news:", len(items), "saved ->", NEWS_ITEMS_CSV)
    return items


def extract_pdf_with_keywords(keywords, window=1, skip_first_pages=6):
    r = http_get(PDF_RULE_URL, stream=True, timeout=60)
    pdf_path = os.path.join(RAW_DIR, "tcg_handbook.pdf")

    f = open(pdf_path, "wb")
    for chunk in r.iter_content(chunk_size=1024 * 64):
        if chunk:
            f.write(chunk)
    f.close()

    parts = []
    i = 0
    while i < len(keywords):
        w = str(keywords[i]).strip()
        if w != "":
            parts.append(re.escape(w))
        i += 1
    pattern = re.compile("(" + "|".join(parts) + ")", re.IGNORECASE)

    extracted = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)

        start = skip_first_pages
        if start < 0:
            start = 0
        if start >= total:
            start = 0

        hit = -1
        p = start
        while p < total:
            txt = pdf.pages[p].extract_text() or ""
            txt = normalize_text(txt)

            # skip TOC-like pages
            if "....." in txt or re.search(r"\.{5,}", txt) is not None:
                p += 1
                continue

            if txt != "" and pattern.search(txt) is not None:
                hit = p
                break
            p += 1

        pages = []
        if hit >= 0:
            a = hit - window
            b = hit + window
            if a < 0:
                a = 0
            if b >= total:
                b = total - 1
            x = a
            while x <= b:
                pages.append(x)
                x += 1
        else:
            pages = [0, 1, 2]

        i = 0
        while i < len(pages):
            idx = pages[i]
            txt = pdf.pages[idx].extract_text() or ""
            txt = normalize_text(txt)
            if txt != "":
                extracted.append("--- Page " + str(idx + 1) + " ---\n" + txt + "\n")
            i += 1

    final_text = "\n".join(extracted).strip()
    f = open(PDF_TEXT, "w", encoding="utf-8")
    f.write(final_text + "\n")
    f.close()

    print("pdf: saved ->", PDF_TEXT)
    return final_text


def build_unified(cards_df, news_items, pdf_text):
    records = []

    limit = 50
    i = 0
    while i < len(cards_df) and i < limit:
        row = cards_df.iloc[i].to_dict()

        text = "Card: " + str(row.get("name", ""))
        if row.get("types", ""):
            text = text + " | Types: " + str(row.get("types"))
        if row.get("rarity", ""):
            text = text + " | Rarity: " + str(row.get("rarity"))

        records.append({
            "domain": "tcg",
            "source_type": "json",
            "source": LOCAL_CARDS_JSON,
            "record_type": "card_info",
            "text": text,
            "fields": row
        })
        i += 1

    j = 0
    while j < len(news_items):
        it = news_items[j]
        title = it["title"] if type(it) == dict and "title" in it else ""
        url = it["url"] if type(it) == dict and "url" in it else ""

        records.append({
            "domain": "tcg",
            "source_type": "html",
            "source": HTML_NEWS_URL,
            "record_type": "news_item",
            "text": title + " | " + url,
            "fields": it
        })
        j += 1

    pdf_trim = pdf_text
    if len(pdf_trim) > 7000:
        pdf_trim = pdf_trim[:7000] + "\n...[TRUNCATED]..."

    records.append({
        "domain": "tcg",
        "source_type": "pdf",
        "source": PDF_RULE_URL,
        "record_type": "rules_excerpt",
        "text": pdf_trim,
        "fields": {"note": "excerpt near violation/penalty keywords"}
    })

    write_jsonl(UNIFIED_JSONL, records)
    print("unified:", len(records), "saved ->", UNIFIED_JSONL)


def main():
    cards_df = load_cards_json_to_csv()
    news_items = scrape_news()

    pdf_text = extract_pdf_with_keywords(
        keywords=["penalt", "infraction", "violation", "cheat", "disqual", "prohibit"],
        window=1,
        skip_first_pages=6
    )

    build_unified(cards_df, news_items, pdf_text)


if __name__ == "__main__":
    main()