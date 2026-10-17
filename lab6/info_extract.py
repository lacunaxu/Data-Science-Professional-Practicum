import os
import re
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import pypdf
import pytesseract
import mysql.connector
from pdf2image import convert_from_path

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'oil_lab6'
}


_TESS_CONFIG = "--oem 1 --psm 6"

os.environ["OMP_THREAD_LIMIT"] = "1"


def _ocr_page(pdf_path, page_index):
    images = convert_from_path(pdf_path, dpi=200, first_page=page_index+1, last_page=page_index+1)
    text = pytesseract.image_to_string(images[0], config=_TESS_CONFIG)
    return page_index, text.strip()


def ocr_pdf(pdf_path, workers=None):
    reader = pypdf.PdfReader(pdf_path)
    total = len(reader.pages)
    results = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        results.append((i, text.strip()))

    scanned_indices = [i for i, t in results if len(t) < 30]
    if not scanned_indices:
        return results

    cpu = len(os.sched_getaffinity(0))
    if workers is None:
        workers = cpu
    workers = min(workers, len(scanned_indices))

    print(f"    {len(scanned_indices)}/{total} pages need OCR — {workers} workers (detected {cpu} CPUs)", flush=True)
    futures = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i in scanned_indices:
            futures[pool.submit(_ocr_page, pdf_path, i)] = i
        for done, future in enumerate(as_completed(futures), 1):
            i, text = future.result()
            results[i] = (i, text)
            print(f"    OCR {done}/{len(scanned_indices)} pages done", end="\r", flush=True)
    print()

    return results

_HEADER_PATTERNS = {
    "well_name": [
        r"Well\s+Name\s*[:\|]\s*(.+?)(?:\s{2,}|API|$)",
        r"Well\s+Name\s+and\s+Number\s*\n([^\n]+)",
        r"Well\s+or\s+Facility\s+Name\s*:\s*([^\n]+)",
        r"Well\s+Name\s*[:\|]?\s*([^\n]+)",
    ],
    "operator": [
        r"Operator\s*[:\|]\s*(.+?)(?:\s{2,}|Well|$)",
        r"Well\s+Operator\s*:\s*([^\n]+)",
        r"Operator\s*\n([^\n]+)",
        r"Name\s+of\s+Operator\s*[:\|]?\s*([^\n]+)",
        r"Operator\s*[:\|]?\s*(.+)",
    ],
    "api": [
        r"\b(\d{2}-\d{3}-\d{5})\b",
        r"\b(\d{2}\s*-\s*\d{3}\s*-\s*\d{5})\b",
        r"API\s*#?\s*:?\s*(\d{10})",
    ],
    "ndic_file_no": [
        r"(?:NDIC\s+)?(?:Well\s+)?File\s+No[\s\.]*[:\|]?\s*(\d+)",
        r"NDIC\s+File\s+Number\s*:\s*(\d+)",
    ],
    "job_number":   [r"Enseco\s+Job\s*#\s*[:\|]?\s*(\S+)"],
    "job_type":     [r"Job\s+Type\s*[:\|]?\s*(\S+(?:\s+\S+)?)"],
    "county": [
        r"County[,\s]+State\s*[:\|]?\s*(.+?)(?:\n|$)",
        r"County\s*[:\|]\s*([^\n]+)",
        r"County\s*\n([^\n]+)",
    ],
    "field_name": [
        r"Field(?:\s+Name)?\s*[:\|]\s*([^\n]+)",
        r"Field\s*\n([^\n]+)",
    ],
    "section_twp_range": [
        r"Section\s*[:\|]\s*(\d+).*?Township\s*[:\|]\s*(\d+).*?Range\s*[:\|]\s*(\d+\s*[WE]?)",
        r"Section\s+Township\s*\n(\d+)\s+(\d+\s*N?)\s*\nRange\s*\n(\d+\s*[WE]?)",
        r"Sec(?:tion)?\s+(\d+)\s+T(?:ownship)?\s+(\d+\s*N?)\s+R(?:ange)?\s+(\d+\s*[WE]?)",
    ],
    "shl_location": [r"Well\s+Surface\s+Hole\s+Location.*?:\s*(.+?)(?:\n|$)"],
    "latitude": [
        r"Latitude\s*[:\|]?\s*([\d°'\"\.NSEW\s]+?)(?:\s{2,}|Longitude|$)",
    ],
    "longitude": [
        r"Longitude\s*[:\|]?\s*([\d°'\"\.NSEW\s]+?)(?:\s{2,}|Datum|$)",
    ],
    "datum": [r"Datum\s*[:\|]?\s*(\S+)"],
}

_STIM_PATTERNS = {
    "date_stimulated":        r"Date\s+Stimulated\s*[:\|]?\s*(\S+(?:\s+\S+)?)",
    "stimulated_formation":   r"Stimulated\s+Formation\s*[:\|]?\s*(\S+(?:\s+\S+)?)",
    "top_ft":                 r"Top\s*\(Ft\)\s*Bottom\s*\(Ft\)\s*Stimulation\s+Stages\s*\n\s*(\d+)",
    "bottom_ft":              r"Top\s*\(Ft\)\s*Bottom\s*\(Ft\)\s*Stimulation\s+Stages\s*\n\s*\d+\s+(\d+)",
    "stimulation_stages":     r"Top\s*\(Ft\)\s*Bottom\s*\(Ft\)\s*Stimulation\s+Stages\s*\n\s*\d+\s+\d+\s+(\d+)",
    "volume":                 r"Volume\s+Units\s*\n\s*(\d+)",
    "volume_units":           r"Volume\s+Units\s*\n\s*\d+\s*(\w+)",
    "type_treatment":         r"Type\s+Treatment\s*[:\|]?\s*(.+?)(?:\n|Acid|$)",
    "acid_pct":               r"Acid\s*%\s*[:\|]?\s*([\d\.]+)",
    "lbs_proppant":           r"Lbs\s+Proppant\s*[:\|]?\s*([\d,]+)",
    "max_treatment_pressure": r"Maximum\s+Treatment\s+Pressure\s*\(PSI\)\s*[:\|]?\s*([\d,]+)",
    "max_treatment_rate":     r"Maximum\s+Treatment\s+Rate\s*\(BBLS/Min\)\s*[:\|]?\s*([\d\.]+)",
    "details":                r"Details\s*[:\|]?\s*([\s\S]+?)(?:\n\n|$)",
}


def _first_match(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return m.group(1).strip()
    return "N/A"


def _normalize_coord(raw):
    raw = raw.strip()
    m = re.match(r"(\d+)[°\s]+(\d+)['\s]+(\d+\.?\d*)[\"''\s]*([NSEW])?", raw, re.IGNORECASE)
    if m:
        deg, mn, sec, direction = m.groups()
        decimal = float(deg) + float(mn) / 60 + float(sec) / 3600
        if direction and direction.upper() in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    m = re.search(r"[-]?\d+\.\d+", raw)
    return float(m.group()) if m else raw


def parse_well_header(text):
    record = {}
    for field, patterns in _HEADER_PATTERNS.items():
        record[field] = _first_match(patterns, text)

    if record["section_twp_range"] == "N/A":
        for pat in _HEADER_PATTERNS["section_twp_range"]:
            m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
            if m:
                record["section_twp_range"] = f"Sec {m.group(1)} Twp {m.group(2)} Rng {m.group(3)}".strip()
                break

    record["latitude"]  = _normalize_coord(record["latitude"])
    record["longitude"] = _normalize_coord(record["longitude"])
    return record


def parse_stimulation(text):
    if not re.search(r"stimulat", text, re.IGNORECASE):
        return None
    stim = {}
    for field, pattern in _STIM_PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        stim[field] = m.group(1).strip().replace(",", "") if m else "N/A"
    return stim


_JUNK_PATTERNS = re.compile(
    r"^(and\s+num|number\s+|location|qtr|section|township|range|assignment|n/a$)",
    re.IGNORECASE
)


def _is_valid_well(name, api):
    if name == "N/A" and api == "N/A":
        return False
    if name != "N/A" and (len(name) < 5 or _JUNK_PATTERNS.match(name.strip())):
        return False
    has_real_api  = api != "N/A" and re.search(r"\d{2}-\d{3}-\d{5}", api)
    has_real_name = name != "N/A" and len(name) > 5 and not _JUNK_PATTERNS.match(name.strip())
    return has_real_api or has_real_name


def _find_best_api(text):
    raw = re.findall(
        r"\b(\d{2}\s*-\s*\d{3}\s*-\s*\d{5})\b|API\s*#?\s*:?\s*(\d{10})",
        text, re.IGNORECASE
    )
    candidates = []
    for g1, g2 in raw:
        val = g1 or g2
        val = re.sub(r"\s", "", val)
        if len(val) == 10:
            val = f"{val[:2]}-{val[2:5]}-{val[5:]}"
        val = re.sub(r"-+", "-", val)
        if re.match(r"^\d{2}-\d{3}-\d{5}$", val):
            candidates.append(val)
    return candidates[0] if candidates else "N/A"


def extract_pdf(pdf_path, workers=None):
    pages = ocr_pdf(pdf_path, workers)
    full_text = "\n".join(t for _, t in pages)

    well = parse_well_header(full_text)

    api = _find_best_api(full_text)
    if api != "N/A":
        well["api"] = api

    stim = parse_stimulation(full_text)
    if stim:
        well.update(stim)

    well["source_file"] = os.path.basename(pdf_path)

    name = well.get("well_name", "N/A")
    if not _is_valid_well(name, well.get("api", "N/A")):
        return []
    return [well]


def extract_folder(folder_path, workers=None):
    all_records = []
    for fname in sorted(os.listdir(folder_path)):
        if fname.lower().endswith(".pdf"):
            path = os.path.join(folder_path, fname)
            print(f"  Processing {fname}...")
            records = extract_pdf(path, workers)
            print(f"    → {len(records)} record(s)")
            all_records.extend(records)
    return all_records


def save_to_db(records):
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wells (
            id                      INT AUTO_INCREMENT PRIMARY KEY,
            source_file             VARCHAR(255),
            operator                VARCHAR(255),
            well_name               VARCHAR(255),
            api                     VARCHAR(50),
            job_number              VARCHAR(100),
            job_type                VARCHAR(100),
            county                  VARCHAR(255),
            shl_location            VARCHAR(500),
            latitude                DOUBLE,
            longitude               DOUBLE,
            datum                   VARCHAR(255),
            date_stimulated         VARCHAR(255),
            stimulated_formation    VARCHAR(100),
            top_ft                  INT,
            bottom_ft               INT,
            stimulation_stages      INT,
            volume                  INT,
            volume_units            VARCHAR(255),
            type_treatment          VARCHAR(255),
            acid_pct                DOUBLE,
            lbs_proppant            BIGINT,
            max_treatment_pressure  INT,
            max_treatment_rate      DOUBLE,
            details                 TEXT,
            field_name              VARCHAR(100),
            section_twp_range       VARCHAR(100),
            ndic_file_no            VARCHAR(100),
            well_status             VARCHAR(100),
            well_type               VARCHAR(100),
            well_direction          VARCHAR(10),
            closest_city            VARCHAR(100),
            township_range_section  VARCHAR(100),
            first_production_date   VARCHAR(100),
            last_production_date    VARCHAR(100),
            oil_produced_bbls       INT,
            gas_produced_mcf        INT,
            drillingedge_url        VARCHAR(500),
            drillingedge_county     VARCHAR(100)
        )
    """)

    new_columns = [
        ("field_name",              "VARCHAR(100)"),
        ("section_twp_range",       "VARCHAR(100)"),
        ("ndic_file_no",            "VARCHAR(100)"),
        ("well_direction",          "VARCHAR(10)"),
        ("township_range_section",  "VARCHAR(100)"),
        ("first_production_date",   "VARCHAR(100)"),
        ("last_production_date",    "VARCHAR(100)"),
        ("drillingedge_url",        "VARCHAR(500)"),
        ("drillingedge_county",     "VARCHAR(100)"),
    ]
    widen_columns = [
        ("volume_units",    "VARCHAR(255)"),
        ("datum",           "VARCHAR(255)"),
        ("date_stimulated", "VARCHAR(255)"),
    ]
    cur.execute("SELECT COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'wells'")
    existing = {row[0]: row[1] for row in cur.fetchall()}
    for col, col_type in new_columns:
        if col not in existing:
            cur.execute(f"ALTER TABLE wells ADD COLUMN {col} {col_type}")
    for col, col_type in widen_columns:
        if col in existing and existing[col] < 255:
            cur.execute(f"ALTER TABLE wells MODIFY COLUMN {col} {col_type}")
    conn.commit()

    insert_sql = """
        INSERT INTO wells (
            source_file, operator, well_name, api, job_number, job_type,
            county, field_name, section_twp_range, ndic_file_no,
            shl_location, latitude, longitude, datum,
            date_stimulated, stimulated_formation, top_ft, bottom_ft,
            stimulation_stages, volume, volume_units, type_treatment,
            acid_pct, lbs_proppant, max_treatment_pressure,
            max_treatment_rate, details
        ) VALUES (
            %(source_file)s, %(operator)s, %(well_name)s, %(api)s,
            %(job_number)s, %(job_type)s, %(county)s, %(field_name)s,
            %(section_twp_range)s, %(ndic_file_no)s,
            %(shl_location)s, %(latitude)s, %(longitude)s, %(datum)s,
            %(date_stimulated)s, %(stimulated_formation)s,
            %(top_ft)s, %(bottom_ft)s, %(stimulation_stages)s,
            %(volume)s, %(volume_units)s, %(type_treatment)s,
            %(acid_pct)s, %(lbs_proppant)s, %(max_treatment_pressure)s,
            %(max_treatment_rate)s, %(details)s
        )
    """

    def _int(v):
        try: return int(v)
        except: return None

    def _float(v):
        try: return float(v)
        except: return None

    def _str(v, maxlen=255):
        if v is None or v == "N/A":
            return v
        return str(v)[:maxlen]

    for rec in records:
        row = dict(rec)
        row["top_ft"]                 = _int(rec.get("top_ft"))
        row["bottom_ft"]              = _int(rec.get("bottom_ft"))
        row["stimulation_stages"]     = _int(rec.get("stimulation_stages"))
        row["volume"]                 = _int(rec.get("volume"))
        row["lbs_proppant"]           = _int(rec.get("lbs_proppant"))
        row["max_treatment_pressure"] = _int(rec.get("max_treatment_pressure"))
        row["acid_pct"]               = _float(rec.get("acid_pct"))
        row["max_treatment_rate"]     = _float(rec.get("max_treatment_rate"))
        row["latitude"]               = _float(rec.get("latitude"))
        row["longitude"]              = _float(rec.get("longitude"))
        for col in ["source_file", "operator", "well_name", "api", "job_number",
                    "job_type", "county", "shl_location", "datum", "date_stimulated",
                    "stimulated_formation", "volume_units", "type_treatment",
                    "field_name", "section_twp_range", "ndic_file_no"]:
            row[col] = _str(row.get(col))
        for col in ["date_stimulated", "stimulated_formation", "top_ft", "bottom_ft",
                    "stimulation_stages", "volume", "volume_units", "type_treatment",
                    "acid_pct", "lbs_proppant", "max_treatment_pressure",
                    "max_treatment_rate", "details",
                    "field_name", "section_twp_range", "ndic_file_no"]:
            row.setdefault(col, None)
        cur.execute(insert_sql, row)

    conn.commit()
    cur.close()
    conn.close()


def _preview(records):
    fields = [
        "source_file", "well_name", "api", "operator", "county",
        "latitude", "longitude", "datum", "shl_location",
        "date_stimulated", "stimulated_formation", "top_ft", "bottom_ft",
        "stimulation_stages", "volume", "volume_units", "lbs_proppant",
        "max_treatment_pressure", "max_treatment_rate", "details",
    ]
    for i, rec in enumerate(records, 1):
        print(f"\n{'='*60}")
        print(f"Record {i}/{len(records)}")
        print(f"{'='*60}")
        for f in fields:
            v = rec.get(f, "—")
            print(f"  {f:<26} {v}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract oil well data from PDFs")
    parser.add_argument("folder", help="Folder containing PDF files")
    parser.add_argument("--workers", type=int, default=None,
                        help="OCR worker threads (default: cpu_count)")
    parser.add_argument("--preview", action="store_true",
                        help="Print extracted fields instead of saving to DB")
    args = parser.parse_args()

    print(f"Scanning {args.folder} ...")
    records = extract_folder(args.folder, args.workers)
    print(f"\nTotal records extracted: {len(records)}")

    if args.preview:
        _preview(records)
    else:
        save_to_db(records)
        print("Saved to database.")
