import argparse
import mysql.connector

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'oil_lab6'
}


def ensure_database():
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
    )
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}`")
    conn.commit()
    cur.close()
    conn.close()


def run_extraction(pdf_folder, workers=None):
    from info_extract import extract_folder, save_to_db

    print("=" * 60)
    print("STEP 1: PDF Extraction")
    print("=" * 60)
    records = extract_folder(pdf_folder, workers)
    print(f"\nExtracted {len(records)} records total.")
    save_to_db(records)
    print("Saved to database.")


def run_enrichment():
    from info_enrich import load_wells_from_db, update_well_in_db, enrich_record, _warm_session
    import requests
    import time

    print("\n" + "=" * 60)
    print("STEP 2: Web Enrichment (drillingedge.com)")
    print("=" * 60)

    session = requests.Session()
    _warm_session(session)
    wells = load_wells_from_db()
    for well in wells:
        print(f"  {well.get('well_name','?')} ({well.get('api','?')})")
        enrich_record(session, well)
        update_well_in_db(well["id"], {
            "well_status":              well.get("well_status", "N/A"),
            "well_type":                well.get("well_type", "N/A"),
            "well_direction":           well.get("well_direction", "N/A"),
            "closest_city":             well.get("closest_city", "N/A"),
            "township_range_section":   well.get("township_range_section", "N/A"),
            "first_production_date":    well.get("first_production_date", "N/A"),
            "last_production_date":     well.get("last_production_date", "N/A"),
            "oil_produced_bbls":        well.get("oil_produced_bbls", 0),
            "gas_produced_mcf":         well.get("gas_produced_mcf", 0),
            "drillingedge_url":         well.get("drillingedge_url", "N/A"),
            "drillingedge_county":      well.get("drillingedge_county", "N/A"),
            "latitude":                 well.get("latitude"),
            "longitude":                well.get("longitude"),
            "operator":                 well.get("operator", "N/A"),
        })
        time.sleep(1.5)
    print("Enrichment complete.")


def main():
    parser = argparse.ArgumentParser(description="Oil Wells data pipeline")
    parser.add_argument("--pdf-folder",   required=True, help="Folder with PDF files")
    parser.add_argument("--workers",      type=int, default=None,
                        help="OCR worker threads (default: cpu_count*2)")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--skip-enrich",  action="store_true")
    args = parser.parse_args()

    ensure_database()

    if not args.skip_extract:
        run_extraction(args.pdf_folder, args.workers)

    if not args.skip_enrich:
        run_enrichment()

    print("\nPipeline finished.")
    print("Run `python oil_display.py` to start the web visualization.")


if __name__ == "__main__":
    main()
