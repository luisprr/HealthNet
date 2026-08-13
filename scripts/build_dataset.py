"""Genera el snapshot de datos que la aplicacion usa en produccion.

La descarga de OpenStreetMap solo ocurre aqui. El resultado se versiona en
``data/`` para que el despliegue (Streamlit Community Cloud, contenedores sin
salida a Overpass) arranque sin tocar la red.

    python scripts/build_dataset.py            # descarga y regenera
    python scripts/build_dataset.py --desde-cache   # reutiliza .cache/ local
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app


def _escribir(G, df, origen: str) -> None:
    app.DATA_DIR.mkdir(parents=True, exist_ok=True)
    app.ox.io.save_graphml(G, app.DATA_GRAPH_FILE)
    df.to_json(app.DATA_ENTITIES_FILE, orient="table", force_ascii=False, index=False)

    manifiesto = {
        "signature": app._firma_cache(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": origen,
        "checksums": {
            app.DATA_GRAPH_FILE.name: app._sha256(app.DATA_GRAPH_FILE),
            app.DATA_ENTITIES_FILE.name: app._sha256(app.DATA_ENTITIES_FILE),
        },
    }
    with app.DATA_MANIFEST_FILE.open("w", encoding="utf-8") as archivo:
        json.dump(manifiesto, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument(
        "--desde-cache",
        action="store_true",
        help="Reutiliza .cache/ en vez de descargar de OpenStreetMap.",
    )
    argumentos = analizador.parse_args()

    if argumentos.desde_cache:
        guardado = app._cargar_cache()
        if guardado is None:
            print("No hay un cache local valido en .cache/.", file=sys.stderr)
            return 1
        G, df = guardado
        origen = "cache local"
    else:
        print(f"Descargando {app.PLACE_NAME} de OpenStreetMap...")
        G, df = app.cargar_y_procesar_datos(app.PLACE_NAME)
        origen = "OpenStreetMap"

    app._validar_datos(G, df)
    _escribir(G, df, origen)

    pesos = {
        ruta.name: f"{ruta.stat().st_size / 1024:.0f} KB"
        for ruta in (app.DATA_GRAPH_FILE, app.DATA_ENTITIES_FILE)
    }
    print(f"Snapshot escrito en {app.DATA_DIR.relative_to(BASE_DIR)}")
    print(f"  nodos={G.number_of_nodes()} aristas={G.number_of_edges()}")
    print(f"  entidades={len(df)} {df['tipo'].value_counts().to_dict()}")
    print(f"  {pesos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
