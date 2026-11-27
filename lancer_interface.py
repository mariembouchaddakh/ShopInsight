"""Lance ShopInsight (API + interface) sur un seul port, sans Node.js.

L'interface doit avoir été construite une fois (`cd frontend && npm run build` → frontend/dist).
Usage, depuis la racine du dépôt :
    python lancer_interface.py            # http://localhost:8000
    python lancer_interface.py --port 8080
Les routes /api/... et /docs restent celles de l'API ; toute autre adresse renvoie l'interface.
"""
from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.main import app

DIST = Path(__file__).resolve().parent / "frontend" / "dist"


def attach_frontend() -> None:
    if not (DIST / "index.html").exists():
        raise SystemExit("frontend/dist introuvable : lancez d'abord `cd frontend && npm install && npm run build`.")
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):  # pages de l'application (routage côté navigateur)
        f = DIST / path
        if path and f.is_file() and DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    attach_frontend()
    if not a.no_browser:
        threading.Timer(4, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
    print(f"ShopInsight : http://localhost:{a.port}  (Ctrl+C pour arrêter ; les agents se chargent en ~1 min)")
    uvicorn.run(app, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
