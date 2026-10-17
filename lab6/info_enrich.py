import os
import re
import time

import requests
import mysql.connector
from bs4 import BeautifulSoup

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': os.environ.get('MYSQL_PASSWORD', ''),
    'database': '560_lab6'
}
SEARCH_URL = "https://www.drillingedge.com/search"
BASE_URL   = "https://www.drillingedge.com"


def _warm_session(session):
    """Fetch homepage to get the required session cookie before any search."""
    session.get(BASE_URL, headers=HEADERS, timeout=60)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def search_well(session, api, well_name):
    has_real_api = api and api != "N/A" and re.match(r"^\d{2}-\d{3}-\d{5}$", api.strip())
    candidates = []
    if has_real_api:
        candidates.append({"type": "wells", "well_name": "", "api_no": api})
    if well_name and well_name != "N/A":
        candidates.append({"type": "wells", "well_name": well_name, "api_no": ""})
    if not has_real_api and api and api != "N/A":
        candidates.append({"type": "wells", "well_name": "", "api_no": api})

    for params in candidates:
        resp = session.get(SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table", class_="table wide-table interest_table")
        if table:
            a = table.find("a")
            if a:
                href = a["href"]
                return "https://www.drillingedge.com" + href if href.startswith("/") else href
    return None


def _get_th(well_table, text):
    th = well_table.find("th", string=text)
    if th and th.next_sibling:
        return th.next_sibling.get_text(strip=True) or "N/A"
    return "N/A"


def scrape_well_page(session, url):
    resp = session.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    data = {
        "well_status":              "N/A",
        "well_type":                "N/A",
        "well_direction":           "N/A",
        "closest_city":             "N/A",
        "township_range_section":   "N/A",
        "first_production_date":    "N/A",
        "last_production_date":     "N/A",
        "oil_produced_bbls":        0,
        "gas_produced_mcf":         0,
        "latitude":                 None,
        "longitude":                None,
        "operator":                 "N/A",
        "drillingedge_county":      "N/A",
    }

    meta = soup.find("section", class_="meta_info")
    if meta:
        divs = meta.find_all("div")
        if len(divs) > 2:
            span = divs[2].find("span")
            if span:
                data["operator"] = span.get_text(strip=True)

    for stat in soup.find_all("p", class_="block_stat"):
        span = stat.find("span")
        if not span:
            continue
        val = span.get_text(strip=True)
        label = stat.get_text().replace(val, "").strip().lower()
        if "oil" in label:
            m = re.search(r"[\d,]+", val)
            if m:
                data["oil_produced_bbls"] = int(m.group().replace(",", ""))
        elif "gas" in label or "mcf" in label:
            m = re.search(r"([\d,\.]+[kK]?)", val)
            if m:
                raw = m.group(1).replace(",", "")
                data["gas_produced_mcf"] = int(float(raw[:-1]) * 1000) if raw.lower().endswith("k") else int(float(raw))

    well_table = soup.find("article", class_="well_table")
    if well_table:
        data["well_status"]            = _get_th(well_table, "Well Status")
        data["well_type"]              = _get_th(well_table, "Well Type")
        data["well_direction"]         = _get_th(well_table, "Well Direction")
        data["closest_city"]           = _get_th(well_table, "Closest City")
        data["township_range_section"] = _get_th(well_table, "Township Range Section")
        data["drillingedge_county"]    = _get_th(well_table, "County")
        data["first_production_date"]  = _get_th(well_table, "First Production Date on File")
        data["last_production_date"]   = _get_th(well_table, "Most Recent Production Date on File")

        latlon = _get_th(well_table, "Latitude / Longitude")
        if latlon and latlon != "N/A" and "," in latlon:
            parts = latlon.split(",")
            try:
                data["latitude"]  = float(parts[0].strip())
                data["longitude"] = float(parts[1].strip())
            except ValueError:
                pass

    if data["latitude"] is None:
        try:
            json_resp = session.get(url + "?json", headers=HEADERS, timeout=15).json()
            row = json_resp["data"][0]
            data["latitude"]  = float(row["lat"])
            data["longitude"] = float(row["lon"])
        except Exception:
            pass

    return data


def enrich_record(session, rec):
    api       = rec.get("api", "")
    well_name = rec.get("well_name", "")
    if not api and not well_name:
        return rec

    _empty = {"well_status": "N/A", "well_type": "N/A", "well_direction": "N/A",
              "closest_city": "N/A", "township_range_section": "N/A",
              "first_production_date": "N/A", "last_production_date": "N/A",
              "oil_produced_bbls": 0, "gas_produced_mcf": 0,
              "drillingedge_url": "N/A", "drillingedge_county": "N/A",
              "latitude": None, "longitude": None, "operator": "N/A"}
    try:
        url = search_well(session, api, well_name)
        if url:
            enrichment = scrape_well_page(session, url)
            rec.update(enrichment)
            rec["drillingedge_url"] = url
        else:
            rec.update(_empty)
    except Exception as e:
        rec.update(_empty)
        print(f"    [skipped: {type(e).__name__}]", flush=True)
    return rec


def _selenium_scrape(url):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    driver.get(url)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    html = driver.page_source
    driver.quit()
    return html


def load_wells_from_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM well_data")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def update_well_in_db(well_id, enrichment):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        UPDATE well_data SET
            well_status             = %(well_status)s,
            well_type               = %(well_type)s,
            well_direction          = %(well_direction)s,
            closest_city            = %(closest_city)s,
            township_range_section  = %(township_range_section)s,
            first_production_date   = %(first_production_date)s,
            last_production_date    = %(last_production_date)s,
            oil_produced_bbls       = %(oil_produced_bbls)s,
            gas_produced_mcf        = %(gas_produced_mcf)s,
            drillingedge_url        = %(drillingedge_url)s,
            drillingedge_county     = %(drillingedge_county)s,
            latitude                = COALESCE(%(latitude)s, latitude),
            longitude               = COALESCE(%(longitude)s, longitude),
            operator                = CASE WHEN %(operator)s != 'N/A' THEN %(operator)s ELSE operator END
        WHERE id = %(id)s
    """, {**enrichment, "id": well_id})
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich well data from drillingedge.com")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only enrich this many wells (for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape and print results but do not write to DB")
    args = parser.parse_args()

    session = requests.Session()
    _warm_session(session)
    wells = load_wells_from_db()
    if args.limit:
        wells = wells[:args.limit]

    total = len(wells)
    for n, well in enumerate(wells, 1):
        name = well.get("well_name", "N/A")
        api  = well.get("api", "N/A")
        if name == "N/A" and api == "N/A":
            continue
        enrich_record(session, well)
        found = well.get("drillingedge_url", "N/A") != "N/A"
        status = well.get("well_status", "N/A")
        print(f"  [{n}/{total}] {name} ({api}) → {'found: ' + status if found else 'not found'}", flush=True)
        if args.dry_run:
            if found:
                print(f"    type={well.get('well_type')} city={well.get('closest_city')} "
                      f"oil={well.get('oil_produced_bbls')} gas={well.get('gas_produced_mcf')} "
                      f"lat={well.get('latitude')} lon={well.get('longitude')}")
        else:
            update_well_in_db(well["id"], well)
        time.sleep(1.5)
    print("Done.")
