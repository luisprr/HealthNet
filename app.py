import base64
import hashlib
import html as html_lib
import json
import logging
import math
import os
import random
import tempfile
import time
from itertools import pairwise
from pathlib import Path

import folium
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import shapely
import streamlit as st
from folium.plugins import Fullscreen, LocateControl
from shapely.ops import linemerge
from streamlit.components.v1 import html

PLACE_NAME = "Miraflores, Lima, Peru"
POI_TAGS = {"amenity": ["hospital", "clinic"]}

N_PACIENTES = 200
N_AMBULANCIAS = 40
SEED = 7

SIN_ASIGNAR = "Sin asignar"

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "HealthNetLogo.png"
CACHE_DIR = BASE_DIR / ".cache"
CACHE_GRAPH_FILE = CACHE_DIR / "healthnet.graphml"
CACHE_ENTITIES_FILE = CACHE_DIR / "entidades.json"
CACHE_META_FILE = CACHE_DIR / "metadata.json"
CACHE_VERSION = 2
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60

LOGGER = logging.getLogger("healthnet")

SIMPLIFICAR_GRADOS = 0.00002
PRECISION_GRADOS = 1e-5

C = {
    "bg": "#FFFFFF",
    "lienzo": "#F4F6F6",
    "surface": "#FFFFFF",
    "surface_2": "#F7F9F9",
    "line": "#E2E7E8",
    "line_soft": "#EEF1F2",
    "text": "#1B2426",
    "text_2": "#5A6B70",
    "text_3": "#93A2A7",
    "accent": "#0F766E",
    "accent_hover": "#0C5F59",
    "hospital": "#E05252",
    "clinic": "#9B7EDE",
    "paciente": "#4E7F9E",
    "ambulancia": "#17A08C",
    "ruta": "#D93B48",
    "nav_marca": "#0F766E",
    "nav_valor": "#0F766E",
    "nav_label": "#57767E",
    "nav_sep": "#C4D6D9",
}

COLORES = {
    "hospital": C["hospital"],
    "clinic": C["clinic"],
    "paciente": C["paciente"],
    "ambulancia": C["ambulancia"],
}

ETIQUETAS = {
    "hospital": "Hospital",
    "clinic": "Clínica",
    "paciente": "Paciente",
    "ambulancia": "Ambulancia",
}

PLURALES = {
    "hospital": "Hospitales",
    "clinic": "Clínicas",
    "paciente": "Pacientes",
    "ambulancia": "Ambulancias",
}

PUNTO = {"hospital": "●", "clinic": "◆", "paciente": "○"}

TIPOS_DESTINO = ("hospital", "clinic", "paciente")


def _construir_grafo(lugar):
    ox.settings.use_cache = False
    ox.settings.log_console = False

    G = ox.graph_from_place(lugar, network_type="drive")
    componentes = list(nx.strongly_connected_components(G))
    if not componentes:
        raise RuntimeError(f"OpenStreetMap no devolvio una red vial para {lugar}.")
    G = G.subgraph(max(componentes, key=len)).copy()
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    return G


def _descargar_pois(lugar):
    pois = ox.features_from_place(lugar, POI_TAGS)
    if pois.empty:
        raise RuntimeError(f"No se encontraron hospitales o clinicas en {lugar}.")

    pois = pois[pois.geometry.notna()]
    registros = []
    for indice, poi in pois.iterrows():
        tipo = poi.get("amenity") or "hospital"
        if tipo not in POI_TAGS["amenity"]:
            continue
        centro = poi.geometry.representative_point()
        nombre = poi.get("name")
        if not isinstance(nombre, str) or not nombre.strip():
            nombre = f"{ETIQUETAS.get(tipo, str(tipo).capitalize())} sin nombre"
        partes_id = indice if isinstance(indice, tuple) else (indice,)
        registros.append(
            {
                "entity_id": "osm:" + ":".join(map(str, partes_id)),
                "lat": centro.y,
                "lon": centro.x,
                "tipo": tipo,
                "nombre": nombre,
            }
        )
    if not registros:
        raise RuntimeError(
            f"No se encontraron hospitales o clinicas validos en {lugar}."
        )
    return registros


def _generar_moviles(G, rng):
    disponibles = list(G.nodes())
    total = N_PACIENTES + N_AMBULANCIAS
    if len(disponibles) < total:
        raise RuntimeError(
            f"La red solo tiene {len(disponibles)} nodos y se requieren {total} "
            "para ubicar pacientes y ambulancias sin duplicados."
        )
    elegidos = iter(rng.sample(disponibles, total))
    registros = []

    for prefijo, tipo, cantidad in (
        ("Paciente", "paciente", N_PACIENTES),
        ("Ambulancia", "ambulancia", N_AMBULANCIAS),
    ):
        for i in range(1, cantidad + 1):
            n = next(elegidos)
            registros.append(
                {
                    "entity_id": f"{tipo}:{i}",
                    "lat": G.nodes[n]["y"],
                    "lon": G.nodes[n]["x"],
                    "tipo": tipo,
                    "nombre": f"{prefijo} {i}",
                    "node_id": n,
                }
            )

    return registros


def _asignar_nodos_cercanos(G, df):
    if "node_id" not in df.columns:
        df["node_id"] = pd.NA

    faltantes = df["node_id"].isna()
    if not faltantes.any():
        return df

    ids = list(G.nodes())
    xs = np.array([G.nodes[n]["x"] for n in ids])
    ys = np.array([G.nodes[n]["y"] for n in ids])

    def mas_cercano(lat, lon):
        d2 = (xs - lon) ** 2 + (ys - lat) ** 2
        return ids[int(d2.argmin())]

    df.loc[faltantes, "node_id"] = [
        mas_cercano(lat, lon)
        for lat, lon in zip(df.loc[faltantes, "lat"], df.loc[faltantes, "lon"])
    ]
    return df


def cargar_y_procesar_datos(lugar):
    rng = random.Random(SEED)

    G = _construir_grafo(lugar)
    registros = _descargar_pois(lugar) + _generar_moviles(G, rng)

    df = pd.DataFrame(registros)
    df = _asignar_nodos_cercanos(G, df)
    df["node_id"] = df["node_id"].astype("int64")

    # Los nombres alimentan los selectores, asi que deben ser unicos.
    duplicados = df["nombre"].duplicated(keep=False)
    if duplicados.any():
        df.loc[duplicados, "nombre"] = (
            df.loc[duplicados, "nombre"]
            + " #"
            + (df.loc[duplicados].groupby("nombre").cumcount() + 1).astype(str)
        )

    _validar_datos(G, df)
    return G, df


def _firma_cache():
    return {
        "version": CACHE_VERSION,
        "lugar": PLACE_NAME,
        "poi_tags": POI_TAGS,
        "pacientes": N_PACIENTES,
        "ambulancias": N_AMBULANCIAS,
        "seed": SEED,
        "network_type": "drive",
        "strong_component": True,
    }


def _validar_datos(G, df):
    requeridas = {"entity_id", "lat", "lon", "tipo", "nombre", "node_id"}
    if G.number_of_nodes() == 0 or not nx.is_strongly_connected(G):
        raise ValueError(
            "La red vial debe ser un grafo dirigido fuertemente conectado."
        )
    if df.empty or not requeridas.issubset(df.columns):
        raise ValueError(
            "El conjunto de entidades esta vacio o tiene un esquema invalido."
        )
    if df["entity_id"].isna().any() or df["entity_id"].duplicated().any():
        raise ValueError("Cada entidad debe tener un identificador unico.")
    if df[["lat", "lon", "tipo", "nombre", "node_id"]].isna().any().any():
        raise ValueError("Las entidades contienen valores obligatorios vacios.")
    coordenadas = df[["lat", "lon"]].to_numpy(dtype=float)
    if not np.isfinite(coordenadas).all():
        raise ValueError("Las entidades contienen coordenadas no finitas.")
    if not df["lat"].between(-90, 90).all() or not df["lon"].between(-180, 180).all():
        raise ValueError("Las entidades contienen coordenadas fuera de rango.")
    if not set(df["tipo"]).issubset(COLORES):
        raise ValueError("Las entidades contienen tipos desconocidos.")
    if not set(map(int, df["node_id"])).issubset(G.nodes):
        raise ValueError("Hay entidades ancladas fuera de la red vial.")
    for _, _, datos in G.edges(data=True):
        tiempo_viaje = datos.get("travel_time")
        if (
            tiempo_viaje is None
            or not math.isfinite(float(tiempo_viaje))
            or float(tiempo_viaje) <= 0
        ):
            raise ValueError("La red contiene aristas sin tiempo de viaje valido.")


def _sha256(ruta):
    resumen = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def _cargar_cache():
    archivos = (CACHE_GRAPH_FILE, CACHE_ENTITIES_FILE, CACHE_META_FILE)
    if not all(archivo.exists() for archivo in archivos):
        return None
    try:
        with CACHE_META_FILE.open("r", encoding="utf-8") as archivo:
            metadata = json.load(archivo)
        if metadata.get("signature") != _firma_cache():
            return None
        creado = float(metadata["created_at"])
        if time.time() - creado > CACHE_TTL_SECONDS:
            LOGGER.info("El cache geografico expiro y se actualizara.")
            return None
        checksums = metadata.get("checksums", {})
        if checksums != {
            CACHE_GRAPH_FILE.name: _sha256(CACHE_GRAPH_FILE),
            CACHE_ENTITIES_FILE.name: _sha256(CACHE_ENTITIES_FILE),
        }:
            raise ValueError(
                "Los archivos del cache no superaron la verificacion SHA-256."
            )
        G = ox.io.load_graphml(CACHE_GRAPH_FILE)
        df = pd.read_json(CACHE_ENTITIES_FILE, orient="table")
        df["node_id"] = df["node_id"].astype("int64")
        _validar_datos(G, df)
        return G, df
    except Exception:
        LOGGER.warning(
            "El cache geografico no es valido; se regenerara.", exc_info=True
        )
        return None


def _temporal_para(destino):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    descriptor, nombre = tempfile.mkstemp(
        prefix=f".{destino.name}.", suffix=".tmp", dir=CACHE_DIR
    )
    os.close(descriptor)
    return Path(nombre)


def _guardar_cache(G, df):
    temporales = {
        CACHE_GRAPH_FILE: _temporal_para(CACHE_GRAPH_FILE),
        CACHE_ENTITIES_FILE: _temporal_para(CACHE_ENTITIES_FILE),
        CACHE_META_FILE: _temporal_para(CACHE_META_FILE),
    }
    try:
        ox.io.save_graphml(G, temporales[CACHE_GRAPH_FILE])
        df.to_json(
            temporales[CACHE_ENTITIES_FILE],
            orient="table",
            force_ascii=False,
            index=False,
        )
        with temporales[CACHE_META_FILE].open("w", encoding="utf-8") as archivo:
            json.dump(
                {
                    "signature": _firma_cache(),
                    "created_at": time.time(),
                    "checksums": {
                        CACHE_GRAPH_FILE.name: _sha256(temporales[CACHE_GRAPH_FILE]),
                        CACHE_ENTITIES_FILE.name: _sha256(
                            temporales[CACHE_ENTITIES_FILE]
                        ),
                    },
                },
                archivo,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        os.replace(temporales[CACHE_GRAPH_FILE], CACHE_GRAPH_FILE)
        os.replace(temporales[CACHE_ENTITIES_FILE], CACHE_ENTITIES_FILE)
        os.replace(temporales[CACHE_META_FILE], CACHE_META_FILE)
    finally:
        for temporal in temporales.values():
            if temporal.exists():
                try:
                    temporal.unlink()
                except OSError:
                    LOGGER.warning("No se pudo retirar el temporal %s.", temporal)


@st.cache_resource(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def cargar_datos():
    guardado = _cargar_cache()
    if guardado is not None:
        return guardado

    G, df = cargar_y_procesar_datos(PLACE_NAME)
    try:
        _guardar_cache(G, df)
    except Exception:
        LOGGER.warning("No se pudo guardar el cache geografico.", exc_info=True)
    return G, df


def calcular_ruta_optima(G, origen, destino):
    try:
        ruta = nx.dijkstra_path(G, origen, destino, weight="travel_time")
        return ruta, nx.path_weight(G, ruta, weight="travel_time")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None, None


def _matriz_tiempos(G, nodos):
    n = len(nodos)
    matriz = [[math.inf] * n for _ in range(n)]
    for i, origen in enumerate(nodos):
        try:
            distancias = nx.single_source_dijkstra_path_length(
                G, origen, weight="travel_time"
            )
        except nx.NodeNotFound:
            continue
        for j, destino in enumerate(nodos):
            matriz[i][j] = 0.0 if i == j else distancias.get(destino, math.inf)
    return matriz


def _costo(orden, matriz):
    return sum(matriz[a][b] for a, b in pairwise(orden))


def _vecino_mas_cercano(matriz):
    pendientes = set(range(1, len(matriz)))
    orden = [0]
    actual = 0

    while pendientes:
        seguros = [
            j
            for j in pendientes
            if math.isfinite(matriz[actual][j])
            and all(math.isfinite(matriz[j][otro]) for otro in pendientes if otro != j)
        ]
        if not seguros:
            return orden, sorted(pendientes)
        siguiente = min(seguros, key=lambda j: matriz[actual][j])
        orden.append(siguiente)
        pendientes.discard(siguiente)
        actual = siguiente

    return orden, []


def _dos_opt(orden, matriz):
    if len(orden) <= 3:
        return orden

    mejor = orden[:]
    mejor_costo = _costo(mejor, matriz)
    hubo_mejora = True

    while hubo_mejora:
        hubo_mejora = False
        for i in range(1, len(mejor) - 1):
            for k in range(i + 1, len(mejor)):
                candidato = mejor[:i] + mejor[i : k + 1][::-1] + mejor[k + 1 :]
                costo = _costo(candidato, matriz)
                if costo < mejor_costo - 1e-9:
                    mejor, mejor_costo = candidato, costo
                    hubo_mejora = True
    return mejor


def calcular_ruta_tsp(G, nodo_origen, nodos_destino):
    puntos = [nodo_origen] + list(nodos_destino)
    if len(puntos) < 2:
        return {
            "ruta": [],
            "tiempo": 0.0,
            "orden_nodos": [nodo_origen],
            "orden_indices": [0],
            "no_visitados": [],
            "error": None,
        }

    matriz = _matriz_tiempos(G, puntos)
    problematicos = {j for j in range(1, len(puntos)) if math.isinf(matriz[0][j])}
    for i in range(1, len(puntos)):
        for j in range(i + 1, len(puntos)):
            if math.isinf(matriz[i][j]) and math.isinf(matriz[j][i]):
                problematicos.update((i, j))
    if problematicos:
        return {
            "ruta": [],
            "tiempo": 0.0,
            "orden_nodos": [],
            "orden_indices": [],
            "no_visitados": sorted(problematicos),
            "error": "Los destinos no se pueden conectar en un unico recorrido dirigido.",
        }

    orden_inicial, pendientes = _vecino_mas_cercano(matriz)
    if pendientes:
        return {
            "ruta": [],
            "tiempo": 0.0,
            "orden_nodos": [],
            "orden_indices": [],
            "no_visitados": pendientes,
            "error": "No se encontro un orden que visite todos los destinos.",
        }

    orden_idx = _dos_opt(orden_inicial, matriz)
    orden = [puntos[i] for i in orden_idx]

    ruta_completa, tiempo_total = [], 0.0
    for i in range(len(orden) - 1):
        tramo, tiempo = calcular_ruta_optima(G, orden[i], orden[i + 1])
        if tramo is None:
            return {
                "ruta": [],
                "tiempo": 0.0,
                "orden_nodos": [],
                "orden_indices": [],
                "no_visitados": orden_idx[i + 1 :],
                "error": "La red cambio durante el calculo y la ruta quedo incompleta.",
            }
        ruta_completa.extend(tramo if not ruta_completa else tramo[1:])
        tiempo_total += tiempo

    return {
        "ruta": ruta_completa,
        "tiempo": tiempo_total,
        "orden_nodos": orden,
        "orden_indices": orden_idx,
        "no_visitados": [],
        "error": None,
    }


def geojson_ruta(G, ruta):
    if not ruta or len(ruta) < 2:
        return None
    tramos = ox.routing.route_to_gdf(G, ruta, weight="travel_time")

    limpias = shapely.set_precision(
        shapely.simplify(np.asarray(tramos.geometry.values), SIMPLIFICAR_GRADOS),
        PRECISION_GRADOS,
    )
    lineas = [g for g in limpias if g is not None and not g.is_empty]
    if not lineas:
        return None

    unida = linemerge(shapely.MultiLineString(lineas)) if len(lineas) > 1 else lineas[0]
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": shapely.geometry.mapping(unida),
                }
            ],
        },
        separators=(",", ":"),
    )


_CSS_MAPA = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700;900&display=swap');

.leaflet-container, .leaflet-control, .leaflet-popup-content {
  font-family: 'Merriweather', Georgia, serif !important;
}
.leaflet-container { background: LIENZO; }
.leaflet-div-icon { background: transparent; border: none; }

.mk-inst {
  display: flex; align-items: center; justify-content: center;
  border-radius: 7px; color: #fff; font-weight: 700; line-height: 1;
  box-shadow: 0 1px 3px rgba(27,36,38,.28);
}
.mk-parada {
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%; background: #fff; border: 2px solid RUTA;
  color: RUTA; font-weight: 700; line-height: 1;
  box-shadow: 0 1px 4px rgba(27,36,38,.25);
}
.mk-origen {
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%; background: AMBULANCIA; border: 2px solid #fff;
  color: #fff; font-weight: 700; line-height: 1;
  box-shadow: 0 1px 4px rgba(27,36,38,.3);
}

.leaflet-popup-content-wrapper {
  background: #fff; color: TEXT; border: 1px solid LINE;
  border-radius: 8px; box-shadow: 0 4px 14px rgba(27,36,38,.12); padding: 1px;
}
.leaflet-popup-content { margin: 11px 14px; font-size: 12.5px; line-height: 1.5; }
.leaflet-popup-tip { background: #fff; box-shadow: none; }
.leaflet-popup-close-button { color: TEXT3 !important; }
.pop-tipo {
  font-size: 9.5px; letter-spacing: .1em; text-transform: uppercase;
  color: TEXT3; display: block; margin-bottom: 3px;
}
.pop-nombre { font-size: 13px; font-weight: 700; color: TEXT; }
.pop-rol {
  display: inline-block; margin-top: 7px; padding: 2px 7px; border-radius: 4px;
  background: rgba(RUTARGB,.1); color: RUTA;
  font-size: 9.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
}

.leaflet-bar, .leaflet-control-layers {
  background: #fff !important; border: 1px solid LINE !important;
  border-radius: 8px !important; box-shadow: 0 1px 3px rgba(27,36,38,.08) !important;
  overflow: hidden;
}
.leaflet-bar a, .leaflet-bar a:hover {
  background: #fff; color: TEXT2; border-bottom: 1px solid LINESOFT;
  width: 30px; height: 30px; line-height: 30px;
}
.leaflet-bar a:hover { background: SURFACE2; color: TEXT; }
.leaflet-bar a:last-child { border-bottom: none; }

.leaflet-control-layers-expanded { padding: 11px 13px 11px 11px; }
.leaflet-control-layers-list::before {
  content: 'Capas'; display: block;
  font-size: 9.5px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: TEXT3; margin: 0 0 8px 2px;
}
.leaflet-control-layers-list label {
  display: block; margin: 4px 0; cursor: pointer;
  font-size: 12px; color: TEXT;
}
.leaflet-control-layers-list label > div { display: flex; align-items: center; }
.leaflet-control-layers-selector { accent-color: ACCENT; margin: 0 8px 0 0; }
.cap-dot {
  width: 7px; height: 7px; border-radius: 50%;
  display: inline-block; margin-right: 7px; flex: none;
}
.leaflet-control-layers-separator { display: none; }

.leaflet-control-attribution {
  background: rgba(255,255,255,.86) !important; color: TEXT3 !important;
  font-size: 9.5px !important; border-radius: 5px 0 0 0;
}
.leaflet-control-attribution a { color: TEXT2 !important; }
.leaflet-control-scale-line {
  background: rgba(255,255,255,.8); border: 1px solid LINE; border-top: none;
  color: TEXT2; font-size: 9.5px;
}

.hn-leyenda {
  position: absolute; bottom: 24px; right: 12px; z-index: 800;
  background: #fff; border: 1px solid LINE; border-radius: 8px;
  box-shadow: 0 1px 3px rgba(27,36,38,.08);
  padding: 11px 14px; color: TEXT; font-size: 12px; line-height: 1.75;
}
.hn-leyenda b {
  display: block; font-size: 9.5px; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: TEXT3; margin-bottom: 7px;
}
.hn-leyenda i {
  width: 8px; height: 8px; border-radius: 50%;
  display: inline-block; margin-right: 9px; vertical-align: middle;
}
.hn-leyenda .barra {
  width: 16px; height: 3px; border-radius: 2px; background: RUTA;
  display: inline-block; margin-right: 9px; vertical-align: middle;
}
@media (max-width: 640px) { .hn-leyenda { display: none; } }
</style>
"""


def _rgb(hexadecimal):
    h = hexadecimal.lstrip("#")
    return ",".join(str(int(h[i : i + 2], 16)) for i in (0, 2, 4))


def _css_mapa():
    reemplazos = {
        "LINESOFT": C["line_soft"],
        "LINE": C["line"],
        "LIENZO": C["lienzo"],
        "SURFACE2": C["surface_2"],
        "TEXT3": C["text_3"],
        "TEXT2": C["text_2"],
        "TEXT": C["text"],
        "ACCENT": C["accent"],
        "AMBULANCIA": C["ambulancia"],
        "RUTARGB": _rgb(C["ruta"]),
        "RUTA": C["ruta"],
    }
    css = _CSS_MAPA
    for clave, valor in reemplazos.items():
        css = css.replace(clave, valor)
    return css


def _icono(clase, contenido, tam, fuente, extra=""):
    return folium.DivIcon(
        icon_size=(tam, tam),
        icon_anchor=(tam // 2, tam // 2),
        popup_anchor=(0, -tam // 2 - 2),
        html=(
            f'<div class="{clase}" style="width:{tam}px;height:{tam}px;'
            f'font-size:{fuente}px;{extra}">{contenido}</div>'
        ),
    )


def _popup(nombre, tipo, rol=""):
    nombre_seguro = html_lib.escape(str(nombre))
    tipo_seguro = html_lib.escape(str(ETIQUETAS.get(tipo, tipo)))
    rol_seguro = html_lib.escape(str(rol))
    marca = f'<span class="pop-rol">{rol_seguro}</span>' if rol else ""
    return folium.Popup(
        f'<span class="pop-tipo">{tipo_seguro}</span>'
        f'<span class="pop-nombre">{nombre_seguro}</span>{marca}',
        max_width=250,
    )


def _leyenda():
    filas = "".join(
        f'<div><i style="background:{COLORES[t]}"></i>{ETIQUETAS[t]}</div>'
        for t in ("hospital", "clinic", "paciente", "ambulancia")
    )
    return (
        f'<div class="hn-leyenda"><b>Leyenda</b>{filas}'
        f'<div><span class="barra"></span>Ruta de emergencia</div></div>'
    )


def _nombre_capa(tipo):
    return f'<i class="cap-dot" style="background:{COLORES[tipo]}"></i>{PLURALES[tipo]}'


def _capas_entidades(m, df, paradas):
    capas = {t: folium.FeatureGroup(name=_nombre_capa(t), show=True) for t in COLORES}

    for fila in df.itertuples():
        tipo = fila.tipo
        capa = capas.get(tipo)
        if capa is None or fila.entity_id in paradas:
            continue

        coords = (fila.lat, fila.lon)
        popup = _popup(fila.nombre, tipo)

        if tipo in ("hospital", "clinic"):
            folium.Marker(
                coords,
                popup=popup,
                tooltip=html_lib.escape(str(fila.nombre)),
                icon=_icono("mk-inst", "+", 21, 14, f"background:{COLORES[tipo]};"),
            ).add_to(capa)
        else:
            grande = tipo == "ambulancia"
            folium.CircleMarker(
                coords,
                radius=4.2 if grande else 3.4,
                color=COLORES[tipo],
                weight=0,
                fill=True,
                fill_color=COLORES[tipo],
                fill_opacity=0.95 if grande else 0.8,
                popup=popup,
                tooltip=html_lib.escape(str(fila.nombre)),
            ).add_to(capa)

    for capa in capas.values():
        capa.add_to(m)


def _capa_ruta(m, G, ruta, paradas, indice):
    grupo = folium.FeatureGroup(name="Ruta de emergencia", show=True, control=False)

    traza = geojson_ruta(G, ruta)
    if traza:
        folium.GeoJson(
            traza,
            style_function=lambda _: {
                "color": C["ruta"],
                "weight": 2.6,
                "opacity": 1,
                "lineCap": "round",
                "lineJoin": "round",
            },
        ).add_to(grupo)

    repeticiones = {}
    for entity_id in paradas:
        nid = indice[entity_id][0]
        repeticiones[nid] = repeticiones.get(nid, 0) + 1
    vistos = {}

    for i, entity_id in enumerate(paradas):
        nid, nombre, tipo, lat, lon = indice[entity_id]
        total_nodo = repeticiones[nid]
        posicion = vistos.get(nid, 0)
        vistos[nid] = posicion + 1
        if total_nodo > 1:
            angulo = 2 * math.pi * posicion / total_nodo
            lat += 0.000025 * math.cos(angulo)
            lon += 0.000025 * math.sin(angulo) / max(math.cos(math.radians(lat)), 0.2)
        if i == 0:
            icono, rol = _icono("mk-origen", "A", 24, 11), "Origen"
        else:
            icono, rol = _icono("mk-parada", str(i), 23, 11), f"Parada {i}"
        folium.Marker(
            (lat, lon), icon=icono, popup=_popup(nombre, tipo, rol), tooltip=rol
        ).add_to(grupo)

    grupo.add_to(m)


def generar_mapa(G, df, ruta=None, paradas=None):
    m = folium.Map(
        location=[df["lat"].mean(), df["lon"].mean()],
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
        zoom_control=True,
    )

    folium.TileLayer("cartodbpositron", name="Base", control=False).add_to(m)

    paradas = list(paradas or [])
    ids_parada = set(paradas)

    _capas_entidades(m, df, ids_parada)

    if ruta and paradas:
        indice = {
            f.entity_id: (f.node_id, f.nombre, f.tipo, f.lat, f.lon)
            for f in df.itertuples()
            if f.entity_id in ids_parada
        }
        _capa_ruta(m, G, ruta, paradas, indice)

    m.fit_bounds(
        [[df["lat"].min(), df["lon"].min()], [df["lat"].max(), df["lon"].max()]],
        padding=(18, 18),
    )

    LocateControl(position="topleft", strings={"title": "Mi ubicación"}).add_to(m)
    Fullscreen(position="topleft", title="Pantalla completa").add_to(m)
    folium.LayerControl(collapsed=False, position="topright").add_to(m)
    m.get_root().html.add_child(folium.Element(_css_mapa() + _leyenda()))

    return m.get_root().render()


@st.cache_data(show_spinner=False, ttl=CACHE_TTL_SECONDS)
def mapa_base(_G, _df, clave):
    """El mapa sin ruta no cambia nunca: se renderiza una sola vez."""
    return generar_mapa(_G, _df)


_FUENTES = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Merriweather:wght@300;400;700;900&display=swap');"
)

_CSS_APP = """
:root {
  --nav-h: 58px;
  --panel-w: 380px;
}

*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp, [class*="st-"], button, input, select, textarea, div, span,
p, h1, h2, h3, h4, h5, h6, li, dt, dd, label, em, b, strong, i {
  font-family: 'Merriweather', Georgia, serif !important;
}
[data-testid="stIconMaterial"], [class*="material-symbols"], span[translate="no"] {
  font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
  font-feature-settings: 'liga' 1 !important;
}

.stApp { background: var(--bg); color: var(--text); }
::selection { background: color-mix(in srgb, var(--accent) 22%, transparent); }

header[data-testid="stHeader"], [data-testid="stToolbar"],
[data-testid="stDecoration"], footer { display: none !important; }
[data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"] { display: none !important; }
[data-testid="stSidebarHeader"] { display: none !important; }


[data-testid="stAppViewContainer"] {
  padding-top: var(--nav-h);
  height: 100vh !important;
  min-height: 100vh !important;
  overflow: hidden;
}

[data-testid="stAppViewContainer"] > *,
section[data-testid="stSidebar"],
[data-testid="stMain"] {
  height: calc(100vh - var(--nav-h)) !important;
  max-height: calc(100vh - var(--nav-h)) !important;
}
html, body { overflow: hidden; }
.stApp .stMainBlockContainer, .stApp .block-container {
  padding: 0 !important; max-width: 100% !important;
}
[data-testid="stMain"] { background: var(--bg); overflow: hidden !important; }

[data-testid="stMain"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stMain"] [data-testid="stElementContainer"]:has(style) {
  display: none !important;
}

[data-testid="stMain"] [data-testid="stElementContainer"]:has(.hn-bar) {
  height: var(--bar-h) !important;
  min-height: var(--bar-h) !important;
  flex: none !important;
}

.stApp .hn-top {
  position: fixed; inset: 0 0 auto 0; height: var(--nav-h); z-index: 1000001;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 clamp(20px, 7vw, 150px);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.stApp .hn-brand { display: flex; align-items: center; gap: 18px; min-width: 0; }
.stApp .hn-brand img { width: 34px; height: 34px; object-fit: contain; flex: none; }
.stApp .hn-word {
  font-size: 22px !important; font-weight: 900; color: var(--nav-marca);
  white-space: nowrap; line-height: 1;
}
.stApp .hn-rule {
  width: 1px; height: 22px; background: var(--nav-sep); flex: none;
}
.stApp .hn-cifras { display: flex; align-items: center; gap: 18px; }
.stApp .hn-cifra {
  display: flex; align-items: baseline; gap: 10px; margin: 0 !important;
}
.stApp .hn-cifra dt {
  font-size: 10px !important; font-weight: 700; letter-spacing: .12em;
  text-transform: uppercase; color: var(--nav-label); margin: 0 !important;
  line-height: 1;
}
.stApp .hn-cifra dd {
  font-size: 15px !important; font-weight: 700; color: var(--nav-valor);
  margin: 0 !important; line-height: 1;
}

section[data-testid="stSidebar"] {
  background: var(--surface); border-right: 1px solid var(--line);
  width: var(--panel-w) !important; min-width: var(--panel-w) !important;
}
section[data-testid="stSidebar"] > div:first-child { padding: 22px 24px 30px 24px; }
section[data-testid="stSidebar"] .block-container { padding: 0 !important; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
  padding-bottom: 24px !important;
}

section[data-testid="stSidebar"] [data-testid="stElementContainer"] {
  margin: 0; flex-shrink: 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.hn-paso) {
  padding: 36px 0 15px 0;
}
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.hn-nota) {
  padding: 15px 0 26px 0;
}
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.hn-algo) {
  padding: 18px 0 24px 0;
}
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.hn-ficha) {
  padding-top: 30px;
}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:last-child { padding-top: 24px; }

.stApp .hn-paso {
  display: flex; align-items: center; gap: 9px;
  font-size: 10px !important; font-weight: 700; letter-spacing: .14em;
  text-transform: uppercase; color: var(--text-3);
  margin: 0 !important; line-height: 1;
}
.stApp .hn-paso b { color: var(--text-2); font-weight: 700; }
.stApp .hn-paso i { font-style: normal; color: var(--text-3); }
.stApp .hn-paso::after { content: ''; flex: 1; height: 1px; background: var(--line); }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:first-child { padding-top: 0 !important; }

.stApp .hn-nota {
  font-size: 11.5px !important; color: var(--text-3); line-height: 1.5 !important;
  margin: 0 !important; font-weight: 300;
}
.stApp .hn-nota b { color: var(--text-2); font-weight: 700; }
.stApp .hn-algo {
  font-size: 11px !important; color: var(--text-3); line-height: 1.8 !important;
  margin: 0 !important; font-weight: 300;
}
.stApp .hn-algo b { color: var(--text-2); font-weight: 700; }

.stApp div[data-baseweb="select"] > div {
  background: var(--surface) !important;
  border: 1px solid var(--line) !important;
  border-radius: 9px !important; color: var(--text) !important;
  min-height: 46px; box-shadow: none !important; font-size: 13px !important;
  padding: 3px 6px !important;
  transition: border-color .15s ease;
}
.stApp div[data-baseweb="select"] > div:hover { border-color: var(--text-3) !important; }
.stApp div[data-baseweb="select"] > div[aria-expanded="true"],
.stApp div[data-baseweb="select"] > div:focus-within {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 13%, transparent) !important;
}
.stApp div[data-baseweb="select"] svg { color: var(--text-3) !important; }
.stApp div[data-baseweb="select"] input { color: var(--text) !important; }

div[data-baseweb="popover"] ul[role="listbox"],
div[data-baseweb="popover"] div[role="listbox"] {
  background: var(--surface) !important;
  border: 1px solid var(--line) !important;
  border-radius: 9px !important; padding: 5px !important;
  box-shadow: 0 6px 20px rgba(27,36,38,.1) !important;
}
li[role="option"] {
  color: var(--text-2) !important; border-radius: 6px !important;
  font-size: 12.5px !important; padding: 9px 10px !important;
}
li[role="option"]:hover, li[role="option"][aria-selected="true"] {
  background: var(--surface-2) !important; color: var(--text) !important;
}
.stApp span[data-baseweb="tag"] {
  background: var(--surface) !important;
  border: 1px solid var(--line) !important;
  color: var(--text) !important; border-radius: 999px !important;
  font-size: 11.5px !important; font-weight: 400 !important;
  height: auto !important; max-width: 100% !important;
  margin: 3px 4px 3px 0 !important; padding: 4px 3px 4px 9px !important;
}
.stApp span[data-baseweb="tag"] span { color: var(--text) !important; }
.stApp span[data-baseweb="tag"] svg { fill: var(--text-3) !important; }
.stApp span[data-baseweb="tag"]:hover svg { fill: var(--text) !important; }

.stApp .stButton, .stApp .stButton > button { width: 100%; }
.stApp .stButton > button {
  border-radius: 9px !important; font-size: 13px !important; font-weight: 700;
  padding: 11px 10px !important; min-height: 46px;
  border: 1px solid transparent; box-shadow: none !important;
  transition: background .15s ease, border-color .15s ease, color .15s ease;
}
.stApp .stButton > button[kind="primary"] {
  background: var(--accent) !important; color: #fff !important;
  border-color: var(--accent) !important;
}
.stApp .stButton > button[kind="primary"]:hover {
  background: var(--accent-hover) !important; border-color: var(--accent-hover) !important;
}
.stApp .stButton > button[kind="secondary"] {
  background: var(--surface) !important; color: var(--text) !important;
  border-color: var(--line) !important;
}
.stApp .stButton > button[kind="secondary"]:hover {
  background: var(--surface-2) !important; border-color: var(--text-3) !important;
}
.stApp .stButton > button:disabled, .stApp .stButton > button:disabled:hover {
  background: var(--surface-2) !important; color: var(--text-3) !important;
  border-color: var(--line) !important; opacity: 1 !important; cursor: not-allowed;
}
.stApp .stButton > button:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.stApp [data-testid="stHorizontalBlock"] { gap: 10px !important; }

.stApp .hn-ficha {
  border: 1px solid var(--line); border-radius: 11px;
  padding: 17px 18px; margin: 0; background: var(--surface);
}
.stApp .hn-ficha-tit {
  display: flex; align-items: center; gap: 8px;
  font-size: 10px !important; font-weight: 700; letter-spacing: .13em;
  text-transform: uppercase; color: var(--text-2);
  margin: 0 !important; line-height: 1.3;
}
.stApp .hn-ficha-tit::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: var(--ambulancia); flex: none;
}
.stApp .hn-reloj {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  margin: 14px 0 0 0;
}
.stApp .hn-reloj strong {
  font-size: 32px !important; font-weight: 900; color: var(--text);
  line-height: 1; letter-spacing: -.01em;
}
.stApp .hn-reloj span {
  font-size: 11px !important; color: var(--text-3); font-weight: 300;
}
.stApp .hn-pares { display: flex; gap: 36px; margin: 17px 0 0 0; }
.stApp .hn-par { margin: 0 !important; }
.stApp .hn-par dt {
  font-size: 9px !important; font-weight: 700; letter-spacing: .13em;
  text-transform: uppercase; color: var(--text-3);
  margin: 0 0 5px 0 !important; line-height: 1;
}
.stApp .hn-par dd {
  font-size: 15px !important; font-weight: 700; color: var(--text);
  margin: 0 !important; line-height: 1;
}

.stApp .hn-sec {
  margin: 18px 0 0 0; padding-top: 15px; border-top: 1px solid var(--line-soft);
}
.stApp .hn-sec-tit {
  font-size: 9px !important; font-weight: 700; letter-spacing: .13em;
  text-transform: uppercase; color: var(--text-3);
  margin: 0 0 10px 0 !important; line-height: 1;
}
.stApp .hn-fila {
  display: flex; align-items: center; gap: 11px; padding: 6px 0; min-width: 0;
}
.stApp .hn-fila b {
  width: 20px; height: 20px; border-radius: 5px; flex: none;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--surface-2); border: 1px solid var(--line);
  color: var(--text-2); font-size: 9.5px !important; font-weight: 700;
}
.stApp .hn-fila.origen b {
  background: var(--ambulancia); border-color: var(--ambulancia); color: #fff;
}
.stApp .hn-fila span {
  flex: 1; font-size: 12.5px !important; color: var(--text); min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.stApp .hn-fila em {
  font-style: normal; font-size: 9px !important; font-weight: 700;
  letter-spacing: .11em; text-transform: uppercase; color: var(--text-3);
  flex: none;
}

.stApp .hn-bar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 14px;
  height: 46px; padding: 0 18px; background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.stApp .hn-bar-l { display: flex; align-items: center; gap: 14px; min-width: 0; }
.stApp .hn-bar-tit {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 10px !important; font-weight: 700; letter-spacing: .13em;
  text-transform: uppercase; color: var(--text-2); white-space: nowrap;
}
.stApp .hn-bar-tit::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: var(--ambulancia); flex: none;
}
.stApp .hn-bar-sep { width: 1px; height: 15px; background: var(--line); flex: none; }
.stApp .hn-bar-desc {
  font-size: 12px !important; color: var(--text-2); font-weight: 300;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.stApp .hn-bar-r { display: flex; align-items: center; gap: 22px; }
.stApp .hn-bar-r dl {
  display: flex; align-items: baseline; gap: 9px; margin: 0 !important;
}
.stApp .hn-bar-r dt {
  font-size: 9px !important; font-weight: 700; letter-spacing: .13em;
  text-transform: uppercase; color: var(--text-3); margin: 0 !important;
}
.stApp .hn-bar-r dd {
  font-size: 14px !important; font-weight: 700; color: var(--text);
  margin: 0 !important;
}

[data-testid="stMain"] { --bar-h: 46px; }
[data-testid="stMain"]:not(:has(.hn-bar)) { --bar-h: 0px; }
.stApp [data-testid="stIFrame"],
.stApp [data-testid="stCustomComponentV1"],
.stApp iframe[title="st.iframe"] {
  width: 100% !important;
  height: calc(100vh - var(--nav-h) - var(--bar-h)) !important;
  min-height: 320px;
  border: none !important; display: block;
}
.stApp [data-testid="stElementContainer"]:has(iframe[title="st.iframe"]) {
  height: calc(100vh - var(--nav-h) - var(--bar-h)) !important;
}

.stApp div[data-testid="stAlert"] {
  background: var(--surface-2); border: 1px solid var(--line);
  border-radius: 9px; box-shadow: none; padding: 11px 13px; margin-top: 14px;
}
.stApp div[data-testid="stAlert"] p {
  font-size: 11.5px !important; color: var(--text-2); line-height: 1.5;
}
.stApp div[data-testid="stAlert"] svg { display: none; }

[data-testid="stSpinner"] { color: var(--text-3); }
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #D3DADC; border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-3); }

@media (max-width: 1150px) {
  :root { --panel-w: 330px; }
  .stApp .hn-bar-desc { display: none; }
}
@media (max-width: 820px) {
  .stApp .hn-bar-sep { display: none; }
}
@media (max-width: 720px) {
  :root { --nav-h: 54px; }
  [data-testid="stSidebarHeader"] { display: flex !important; }
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stExpandSidebarButton"] {
    display: flex !important; z-index: 1000002;
  }
  [data-testid="stExpandSidebarButton"] { top: calc(var(--nav-h) + 8px) !important; }
  .stApp .hn-top { padding: 0 13px; }
  .stApp .hn-word { font-size: 17px !important; }
  .stApp .hn-cifras { gap: 14px; }
  .stApp .hn-bar { height: 46px; padding: 0 13px; flex-wrap: nowrap; }
  .stApp .hn-bar-r { gap: 14px; }
}
@media (max-width: 480px) {
  .stApp .hn-bar-r { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}
"""


def aplicar_estilos():
    variables = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in C.items())
    st.markdown(
        f"<style>{_FUENTES}:root{{{variables}}}{_CSS_APP}</style>",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def logo_base64():
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except OSError:
        return None


def barra_superior(logo, n_nodos, n_aristas):
    img = f'<img src="data:image/png;base64,{logo}" alt="">' if logo else ""
    st.markdown(
        f"""
        <div class="hn-top">
          <div class="hn-brand">
            {img}
            <span class="hn-rule"></span>
            <span class="hn-word">HealthNet</span>
          </div>
          <div class="hn-cifras">
            <dl class="hn-cifra"><dt>Nodos</dt><dd>{n_nodos}</dd></dl>
            <span class="hn-rule"></span>
            <dl class="hn-cifra"><dt>Aristas</dt><dd>{n_aristas}</dd></dl>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def paso(numero, titulo):
    numero = html_lib.escape(str(numero))
    titulo = html_lib.escape(str(titulo))
    st.markdown(
        f'<div class="hn-paso"><b>{numero}</b><i>·</i>{titulo}</div>',
        unsafe_allow_html=True,
    )


def nota(cantidad, texto):
    cantidad = html_lib.escape(str(cantidad))
    texto = html_lib.escape(str(texto))
    st.markdown(
        f'<div class="hn-nota"><b>{cantidad}</b> {texto}</div>',
        unsafe_allow_html=True,
    )


def barra_mapa(titulo, detalle, cifras=None):
    celdas = "".join(
        f"<dl><dt>{html_lib.escape(str(k))}</dt><dd>{html_lib.escape(str(v))}</dd></dl>"
        for k, v in (cifras or [])
    )
    separador = '<span class="hn-bar-sep"></span>' if detalle else ""
    titulo = html_lib.escape(str(titulo))
    detalle = html_lib.escape(str(detalle))
    st.markdown(
        "<div class='hn-bar'>"
        f"<div class='hn-bar-l'><span class='hn-bar-tit'>{titulo}</span>"
        f"{separador}<span class='hn-bar-desc'>{detalle}</span></div>"
        f"<div class='hn-bar-r'>{celdas}</div></div>",
        unsafe_allow_html=True,
    )


def ficha_ruta(titulo, tiempo, pares, secuencia=None):
    titulo = html_lib.escape(str(titulo))
    tiempo = html_lib.escape(str(tiempo))
    celdas = "".join(
        f"<dl class='hn-par'><dt>{html_lib.escape(str(k))}</dt>"
        f"<dd>{html_lib.escape(str(v))}</dd></dl>"
        for k, v in pares
    )

    filas = ""
    if secuencia:
        cuerpo = ""
        for i, nombre in enumerate(secuencia):
            clase = "hn-fila origen" if i == 0 else "hn-fila"
            marca = "A" if i == 0 else str(i)
            rol = "Origen" if i == 0 else f"Parada {i}"
            nombre = html_lib.escape(str(nombre))
            cuerpo += (
                f"<div class='{clase}'><b>{marca}</b>"
                f"<span>{nombre}</span><em>{rol}</em></div>"
            )
        filas = (
            f"<div class='hn-sec'><div class='hn-sec-tit'>Secuencia</div>{cuerpo}</div>"
        )

    st.markdown(
        f"<div class='hn-ficha'><div class='hn-ficha-tit'>{titulo}</div>"
        f"<div class='hn-reloj'><strong>{tiempo}</strong><span>tiempo estimado</span></div>"
        f"<div class='hn-pares'>{celdas}</div>{filas}</div>",
        unsafe_allow_html=True,
    )


def formatear_tiempo(segundos):
    minutos, resto = divmod(int(segundos), 60)
    if minutos >= 60:
        horas, minutos = divmod(minutos, 60)
        return f"{horas}h {minutos:02d}m"
    return f"{minutos}m {resto:02d}s"


def estado_inicial():
    st.session_state.setdefault(
        "ruta",
        {
            "tipo": "base",
            "nodos": None,
            "tiempo": None,
            "orden": None,
            "paradas": None,
            "paradas_ids": None,
        },
    )
    st.session_state.setdefault("mapa", None)
    st.session_state.setdefault("aviso", "")
    st.session_state.setdefault("origen_id", SIN_ASIGNAR)
    st.session_state.setdefault("destinos_ids", [])


def resetear():
    st.session_state["ruta"] = {
        "tipo": "base",
        "nodos": None,
        "tiempo": None,
        "orden": None,
        "paradas": None,
        "paradas_ids": None,
    }
    st.session_state["aviso"] = ""
    st.session_state["mapa"] = None
    st.session_state["origen_id"] = SIN_ASIGNAR
    st.session_state["destinos_ids"] = []


def main():
    st.set_page_config(
        page_title="HealthNet",
        page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "+",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    aplicar_estilos()
    estado_inicial()

    with st.spinner("Cargando red vial y puntos de interés..."):
        try:
            G, nodos_df = cargar_datos()
        except Exception as exc:  # noqa: BLE001
            st.error(
                "No se pudieron cargar los datos geográficos. Verifique su conexión "
                f"a internet y vuelva a intentarlo. Detalle: {exc}"
            )
            st.stop()

    barra_superior(logo_base64(), G.number_of_nodes(), G.number_of_edges())

    entidades = nodos_df.set_index("entity_id", drop=False)
    nombre_entidad = entidades["nombre"].to_dict()
    nodo_entidad = entidades["node_id"].astype("int64").to_dict()
    tipo_entidad = entidades["tipo"].to_dict()

    ambulancias = sorted(
        nodos_df.loc[nodos_df["tipo"] == "ambulancia", "entity_id"],
        key=lambda entity_id: (
            len(nombre_entidad[entity_id]),
            nombre_entidad[entity_id],
        ),
    )

    destinos_df = nodos_df[nodos_df["tipo"].isin(TIPOS_DESTINO)]
    destinos_disponibles = sorted(
        destinos_df["entity_id"],
        key=lambda entity_id: (
            len(nombre_entidad[entity_id]),
            nombre_entidad[entity_id],
            entity_id,
        ),
    )

    def etiqueta_origen(entity_id):
        return SIN_ASIGNAR if entity_id == SIN_ASIGNAR else nombre_entidad[entity_id]

    def etiqueta_destino(entity_id):
        return f"{PUNTO[tipo_entidad[entity_id]]} {nombre_entidad[entity_id]}"

    with st.sidebar:
        paso("01", "Ambulancia de origen")
        origen_id = st.selectbox(
            "Ambulancia de origen",
            options=[SIN_ASIGNAR] + ambulancias,
            format_func=etiqueta_origen,
            label_visibility="collapsed",
            key="origen_id",
        )
        nota(len(ambulancias), "unidades disponibles en la red")

        paso("02", "Puntos de destino")
        destinos_sel = st.multiselect(
            "Puntos de destino",
            options=destinos_disponibles,
            format_func=etiqueta_destino,
            placeholder="Buscar hospital, clínica o paciente",
            label_visibility="collapsed",
            key="destinos_ids",
        )
        if destinos_sel:
            plural = (
                "destino seleccionado"
                if len(destinos_sel) == 1
                else "destinos seleccionados"
            )
            nota(len(destinos_sel), plural)
        else:
            nota(len(destinos_disponibles), "puntos disponibles")

        paso("03", "Cálculo de ruta")
        hay_origen = origen_id != SIN_ASIGNAR
        modo = st.session_state["ruta"]["tipo"]
        col_a, col_b = st.columns(2, gap="small")
        btn_simple = col_a.button(
            "Ruta simple",
            key="btn_simple",
            type="primary" if modo == "simple" else "secondary",
            width="stretch",
            disabled=not (hay_origen and destinos_sel),
            help="Requiere una ambulancia de origen y al menos un destino.",
        )
        btn_multiple = col_b.button(
            "Ruta múltiple",
            key="btn_multiple",
            type="primary" if modo == "multiple" else "secondary",
            width="stretch",
            disabled=not (hay_origen and len(destinos_sel) >= 2),
            help="Requiere una ambulancia de origen y al menos dos destinos.",
        )
        st.markdown(
            "<div class='hn-algo'><b>Simple:</b> 1 destino<br>"
            "<b>Múltiple:</b> 2 o más destinos</div>",
            unsafe_allow_html=True,
        )

        if btn_simple:
            if not hay_origen or not destinos_sel:
                st.error("Seleccione una ambulancia de origen y al menos un destino.")
            else:
                destino_id = destinos_sel[0]
                origen_nombre = nombre_entidad[origen_id]
                destino_nombre = nombre_entidad[destino_id]
                src, dst = int(nodo_entidad[origen_id]), int(nodo_entidad[destino_id])
                nodos, tiempo = calcular_ruta_optima(G, src, dst)
                if nodos is not None:
                    st.session_state["aviso"] = (
                        f"Se indicaron {len(destinos_sel)} destinos: la ruta simple "
                        f"solo cubre el primero ({destino_nombre}). Use Ruta múltiple para "
                        "cubrirlos todos."
                        if len(destinos_sel) > 1
                        else ""
                    )
                    st.session_state["ruta"] = {
                        "tipo": "simple",
                        "nodos": nodos,
                        "tiempo": tiempo,
                        "orden": [src, dst],
                        "paradas": [origen_nombre, destino_nombre],
                        "paradas_ids": [origen_id, destino_id],
                    }
                    st.session_state["mapa"] = None
                    st.rerun()
                else:
                    st.error("No existe un trayecto viable entre esos puntos.")

        if btn_multiple:
            if not hay_origen or len(destinos_sel) < 2:
                st.error(
                    "Se requiere una ambulancia de origen y al menos dos destinos."
                )
            else:
                src = int(nodo_entidad[origen_id])
                objetivos = [int(nodo_entidad[entity_id]) for entity_id in destinos_sel]
                resultado = calcular_ruta_tsp(G, src, objetivos)
                if resultado["error"] is None:
                    paradas_ids = [
                        origen_id if indice == 0 else destinos_sel[indice - 1]
                        for indice in resultado["orden_indices"]
                    ]
                    st.session_state["aviso"] = ""
                    st.session_state["ruta"] = {
                        "tipo": "multiple",
                        "nodos": resultado["ruta"],
                        "tiempo": resultado["tiempo"],
                        "orden": resultado["orden_nodos"],
                        "paradas": [nombre_entidad[eid] for eid in paradas_ids],
                        "paradas_ids": paradas_ids,
                    }
                    st.session_state["mapa"] = None
                    st.rerun()
                else:
                    afectados = [
                        nombre_entidad[destinos_sel[indice - 1]]
                        for indice in resultado["no_visitados"]
                        if 0 < indice <= len(destinos_sel)
                    ]
                    detalle = ", ".join(afectados[:5])
                    if len(afectados) > 5:
                        detalle += f" y {len(afectados) - 5} más"
                    st.session_state["ruta"] = {
                        "tipo": "base",
                        "nodos": None,
                        "tiempo": None,
                        "orden": None,
                        "paradas": None,
                        "paradas_ids": None,
                    }
                    st.session_state["mapa"] = None
                    st.error(
                        f"{resultado['error']}"
                        + (f" Destinos afectados: {detalle}." if detalle else "")
                    )

        estado = st.session_state["ruta"]
        if estado["tipo"] == "simple":
            ficha_ruta(
                "Ruta simple calculada",
                formatear_tiempo(estado["tiempo"]),
                [("Destinos", "1"), ("Algoritmo", "Dijkstra")],
                secuencia=estado["paradas"],
            )
        elif estado["tipo"] == "multiple":
            ficha_ruta(
                "Ruta múltiple optimizada",
                formatear_tiempo(estado["tiempo"]),
                [
                    ("Paradas", f"{max(len(estado['orden']) - 1, 0)}"),
                    ("Algoritmo", "2-opt"),
                ],
                secuencia=estado["paradas"],
            )

        if st.session_state["aviso"]:
            st.warning(st.session_state["aviso"])

        st.button(
            "Resetear sistema",
            key="btn_reset",
            type="secondary",
            width="stretch",
            disabled=(
                estado["tipo"] == "base"
                and origen_id == SIN_ASIGNAR
                and not destinos_sel
            ),
            on_click=resetear,
        )

    estado = st.session_state["ruta"]

    if estado["tipo"] == "simple":
        barra_mapa(
            "Ruta simple calculada",
            "Camino de menor tiempo · Dijkstra sobre tiempos de viaje",
            [
                ("Tiempo total", formatear_tiempo(estado["tiempo"])),
                ("Tramos", f"{len(estado['nodos']) - 1}"),
            ],
        )
    elif estado["tipo"] == "multiple":
        barra_mapa(
            "Ruta múltiple optimizada",
            "Vecino más cercano + optimización 2-opt",
            [
                ("Tiempo total", formatear_tiempo(estado["tiempo"])),
                ("Paradas", f"{max(len(estado['orden']) - 1, 0)}"),
            ],
        )

    if st.session_state["mapa"] is None:
        with st.spinner("Trazando mapa..."):
            if estado["tipo"] == "base":
                clave_mapa = json.dumps(_firma_cache(), sort_keys=True)
                st.session_state["mapa"] = mapa_base(G, nodos_df, clave_mapa)
            else:
                st.session_state["mapa"] = generar_mapa(
                    G, nodos_df, estado["nodos"], estado["paradas_ids"]
                )

    html(st.session_state["mapa"], height=760, scrolling=False)


if __name__ == "__main__":
    main()
