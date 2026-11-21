// Where the Flask backend runs, used only when this folder is hosted by a separate static server
// (e.g. `python -m http.server 5500`). When Flask serves the frontend it answers /config.js itself with
// API_BASE = "" (same origin), so this file is ignored there.
window.API_BASE = window.API_BASE ?? "http://127.0.0.1:8000";
