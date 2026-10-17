import json

from flask import Flask, jsonify, render_template_string
import mysql.connector

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'oil_lab6'
}

app = Flask(__name__)

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Oil Wells Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, sans-serif; display: flex; flex-direction: column; height: 100vh; }
    header { background: #1a1a2e; color: #e0e0e0; padding: 10px 20px; display: flex; align-items: center; gap: 12px; }
    header h1 { font-size: 1.2rem; }
    #map { flex: 1; }

    .leaflet-popup-content { max-height: 400px; overflow-y: auto; min-width: 320px; }
    .popup-title { font-size: 1rem; font-weight: bold; color: #1a1a2e; margin-bottom: 8px; border-bottom: 2px solid #e67e22; padding-bottom: 4px; }
    .popup-section { margin-top: 8px; }
    .popup-section h4 { font-size: 0.78rem; text-transform: uppercase; color: #888; letter-spacing: 0.5px; margin-bottom: 4px; }
    .popup-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 10px; font-size: 0.82rem; }
    .popup-grid .label { color: #555; }
    .popup-grid .value { color: #111; font-weight: 500; }
    .badge { display: inline-block; background: #e67e22; color: white; border-radius: 3px; padding: 1px 6px; font-size: 0.78rem; margin-right: 4px; }
    .badge.gas { background: #2980b9; }
    .badge.status-active { background: #27ae60; }
    .badge.status-inactive { background: #c0392b; }
    a.de-link { font-size: 0.78rem; color: #2980b9; }
  </style>
</head>
<body>
  <header>
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#e67e22" stroke-width="2">
      <circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 1 8 8c0 5.25-8 13-8 13S4 15.25 4 10a8 8 0 0 1 8-8z"/>
    </svg>
    <h1>Oil Wells Explorer</h1>
    <span style="margin-left:auto;font-size:0.85rem;color:#aaa" id="well-count"></span>
  </header>
  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const map = L.map('map').setView([47.5, -102.5], 7);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19
    }).addTo(map);

    const oilIcon = L.divIcon({
      className: '',
      html: `<svg width="20" height="28" viewBox="0 0 20 28" xmlns="http://www.w3.org/2000/svg">
               <path d="M10 0C4.48 0 0 4.48 0 10c0 7 10 18 10 18s10-11 10-18C20 4.48 15.52 0 10 0z"
                     fill="#e67e22" stroke="#c0392b" stroke-width="1.5"/>
               <circle cx="10" cy="10" r="4" fill="white"/>
             </svg>`,
      iconAnchor: [10, 28],
      popupAnchor: [0, -28]
    });

    function statusBadge(s) {
      if (!s || s === 'N/A') return '';
      const cls = s.toLowerCase().includes('active') ? 'status-active' : 'status-inactive';
      return `<span class="badge ${cls}">${s}</span>`;
    }

    function row(label, value) {
      if (!value || value === 'N/A' || value === '0' || value === 0) return '';
      return `<div class="label">${label}</div><div class="value">${value}</div>`;
    }

    function buildPopup(w) {
      const lat  = (typeof w.latitude === 'number')  ? w.latitude.toFixed(6)  : w.latitude;
      const lon  = (typeof w.longitude === 'number') ? w.longitude.toFixed(6) : w.longitude;
      const oil  = w.oil_produced_bbls ? `<span class="badge">${w.oil_produced_bbls.toLocaleString()} BBL oil</span>` : '';
      const gas  = w.gas_produced_mcf  ? `<span class="badge gas">${w.gas_produced_mcf.toLocaleString()} MCF gas</span>` : '';
      const link = w.drillingedge_url && w.drillingedge_url !== 'N/A'
        ? `<a class="de-link" href="${w.drillingedge_url}" target="_blank">View on DrillingEdge ↗</a>` : '';

      return `
        <div class="popup-title">${w.well_name || 'Unknown Well'}</div>
        ${statusBadge(w.well_status)}
        <span class="badge" style="background:#555">${w.well_type || 'N/A'}</span>
        <div class="popup-section">
          <h4>Identification</h4>
          <div class="popup-grid">
            ${row('API #', w.api)}
            ${row('Operator', w.operator)}
            ${row('Job #', w.job_number)}
            ${row('Job Type', w.job_type)}
            ${row('County', w.county)}
            ${row('Closest City', w.closest_city)}
          </div>
        </div>
        <div class="popup-section">
          <h4>Location</h4>
          <div class="popup-grid">
            ${row('Latitude', lat)}
            ${row('Longitude', lon)}
            ${row('Datum', w.datum)}
            ${row('SHL', w.shl_location)}
          </div>
        </div>
        <div class="popup-section">
          <h4>Stimulation</h4>
          <div class="popup-grid">
            ${row('Date', w.date_stimulated)}
            ${row('Formation', w.stimulated_formation)}
            ${row('Top (ft)', w.top_ft)}
            ${row('Bottom (ft)', w.bottom_ft)}
            ${row('Stages', w.stimulation_stages)}
            ${row('Volume', w.volume ? w.volume + ' ' + (w.volume_units||'') : '')}
            ${row('Treatment', w.type_treatment)}
            ${row('Acid %', w.acid_pct)}
            ${row('Proppant (lbs)', w.lbs_proppant ? Number(w.lbs_proppant).toLocaleString() : '')}
            ${row('Max Pressure (PSI)', w.max_treatment_pressure)}
            ${row('Max Rate (BBLS/min)', w.max_treatment_rate)}
          </div>
          ${w.details && w.details !== 'N/A' ? `<div style="margin-top:4px;font-size:0.8rem;color:#555">${w.details}</div>` : ''}
        </div>
        <div class="popup-section">
          <h4>Production</h4>
          ${oil} ${gas}
          ${oil === '' && gas === '' ? '<span style="color:#aaa;font-size:0.82rem">No production data</span>' : ''}
        </div>
        ${link ? `<div style="margin-top:8px">${link}</div>` : ''}
      `;
    }

    fetch('/api/wells')
      .then(r => r.json())
      .then(wells => {
        document.getElementById('well-count').textContent = wells.length + ' wells';
        const bounds = [];
        wells.forEach(w => {
          const lat = parseFloat(w.latitude);
          const lon = parseFloat(w.longitude);
          if (!isNaN(lat) && !isNaN(lon)) {
            L.marker([lat, lon], {icon: oilIcon})
              .bindPopup(buildPopup(w), {maxWidth: 380})
              .addTo(map);
            bounds.push([lat, lon]);
          }
        });
        if (bounds.length) map.fitBounds(bounds, {padding: [40, 40]});
      });
  </script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(_HTML)


@app.route("/api/wells")
def api_wells():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM wells")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(rows)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Oil wells map visualization")
    parser.add_argument("--host",  default="0.0.0.0")
    parser.add_argument("--port",  type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"Open http://localhost:{args.port} in your browser.")
    app.run(host=args.host, port=args.port, debug=args.debug)
