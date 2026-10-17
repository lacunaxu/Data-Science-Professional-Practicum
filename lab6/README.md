# Oil Wells Data Pipeline

Extracts oil well data from PDF well files, enriches it with live data from drillingedge.com, and serves an interactive map visualization.

## Scripts

| File | Purpose |
|---|---|
| `oil_info.py` | Main entry point — runs extraction then enrichment |
| `info_extract.py` | OCR and regex extraction from PDFs to MySQL |
| `info_enrich.py` | Scrapes drillingedge.com for each well data and save to MySQL |
| `oil_display.py` | Flask app serving a Leaflet map of all wells |

## Setup

### System dependencies

```bash
# Ubuntu
sudo apt install tesseract-ocr poppler-utils mysql-server
```

### Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database

```bash
mysql -u root -e "CREATE DATABASE IF NOT EXISTS oil_lab6;"
```

The `wells` table is created automatically on first run. Subsequent runs will `ALTER TABLE` to add any new columns without dropping data.

## Running

### Full pipeline (extract + enrich)

```bash
python oil_info.py --pdf-folder ../sampleData
```

### Extract only (skip enrichment)

```bash
python oil_info.py --pdf-folder ../sampleData --skip-enrich
```

### Enrich only (skip extraction)

```bash
python oil_info.py --pdf-folder ../sampleData --skip-extract
```

### Control OCR parallelism

```bash
python oil_info.py --pdf-folder ../sampleData --workers 4
```

Defaults to `cpu_count` workers. Each worker runs one tesseract process; `OMP_THREAD_LIMIT=1` is set automatically so each runs single-threaded.

### Map visualization

```bash
python oil_display.py
# open http://localhost:5000
```

## Testing individual steps

```bash
# Preview extracted fields without writing to DB
python info_extract.py ../sampleData --preview

# Test enrichment on 1 well, dry run (no DB writes)
python info_enrich.py --limit 1 --dry-run

# Real enrichment run on 3 wells
python info_enrich.py --limit 3
```

## Database schema

The `wells` table stores both extracted and enriched data in a single row per PDF.

### Extracted from PDF

| Column | Description |
|---|---|
| `source_file` | PDF filename |
| `well_name` | Well name |
| `api` | API number (XX-XXX-XXXXX format) |
| `ndic_file_no` | NDIC well file number (from NDIC-format docs) |
| `operator` | Well operator |
| `county` | County |
| `field_name` | Field name |
| `section_twp_range` | Section / Township / Range |
| `latitude` / `longitude` | Coordinates (decimal degrees) |
| `datum` | Vertical datum |
| `shl_location` | Surface hole location |
| `date_stimulated` | Stimulation date |
| `stimulated_formation` | Formation name |
| `top_ft` / `bottom_ft` | Stimulation interval (ft) |
| `stimulation_stages` | Number of stages |
| `volume` / `volume_units` | Fluid volume |
| `type_treatment` | Treatment type |
| `acid_pct` | Acid percentage |
| `lbs_proppant` | Proppant weight |
| `max_treatment_pressure` | Max pressure (PSI) |
| `max_treatment_rate` | Max rate (BBLS/min) |

### Enriched from drillingedge.com

| Column | Description |
|---|---|
| `well_status` | Active / Inactive / Plugged |
| `well_type` | Oil & Gas / Water Disposal / etc. |
| `well_direction` | H (horizontal) / V (vertical) |
| `closest_city` | Nearest city |
| `township_range_section` | Township / Range / Section from site |
| `drillingedge_county` | County as listed on drillingedge |
| `first_production_date` | First date on production record |
| `last_production_date` | Most recent date on production record |
| `oil_produced_bbls` | Latest month oil production (BBLs) |
| `gas_produced_mcf` | Latest month gas production (MCF) |
| `drillingedge_url` | Link to well page |

## Notes

- Enrichment tries the real API number first (`XX-XXX-XXXXX`), falls back to well name search.
- Network timeouts during enrichment are caught and logged — the pipeline continues.
# oil_well_database_construction
