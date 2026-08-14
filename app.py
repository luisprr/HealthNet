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
DATA_DIR = BASE_DIR / "data"
DATA_GRAPH_FILE = DATA_DIR / "red_vial.graphml"
DATA_ENTITIES_FILE = DATA_DIR / "entidades.json"
DATA_MANIFEST_FILE = DATA_DIR / "manifiesto.json"

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

TIPOS_DESTINO = ("hospital", "clinic", "paciente")

IDIOMAS = ("es", "en")
IDIOMA_POR_DEFECTO = "es"

TEXTOS = {
    "es": {
        "nodos": "Nodos",
        "aristas": "Aristas",
        "paso_origen": "Ambulancia de origen",
        "paso_destinos": "Destinos",
        "paso_calculo": "Cálculo de ruta",
        "sin_asignar": "Sin asignar",
        "buscar_destino": "Buscar hospital, clínica o paciente",
        "unidades_disponibles": "unidades disponibles en la red",
        "destinos_disponibles": "destinos disponibles",
        "destino_seleccionado": "destino seleccionado",
        "destinos_seleccionados": "destinos seleccionados",
        "quitar_destino": "Quitar {nombre}",
        "btn_simple": "Ruta simple",
        "btn_multiple": "Ruta múltiple",
        "btn_reset": "Resetear sistema",
        "ayuda_simple": "Requiere una ambulancia de origen y al menos un destino.",
        "ayuda_multiple": "Requiere una ambulancia de origen y al menos dos destinos.",
        "hint_simple": "Simple:",
        "hint_simple_val": "1 destino",
        "hint_multiple": "Múltiple:",
        "hint_multiple_val": "2 o más destinos",
        "tiempo_estimado": "tiempo estimado",
        "secuencia": "Secuencia",
        "origen": "Origen",
        "parada": "Parada {n}",
        "destinos": "Destinos",
        "paradas": "Paradas",
        "err_sin_trayecto": "No existe un trayecto viable entre esos puntos.",
        "err_afectados": "Destinos afectados: {detalle}.",
        "err_y_mas": "y {n} más",
        "aviso_multiples": (
            "Se indicaron {total} destinos: la ruta simple solo cubre el primero "
            "({destino}). Use Ruta múltiple para cubrirlos todos."
        ),
        "cargando_titulo": "Preparando la red vial",
        "cargando_detalle": "Cargando calles, hospitales y unidades del distrito",
        "trazando_mapa": "Trazando mapa...",
        "err_datos_titulo": "No se pudieron cargar los datos geográficos",
        "err_datos_ayuda": (
            "La aplicación usa un snapshot incluido en el repositorio. Si falta, "
            "regenérelo con: python scripts/build_dataset.py"
        ),
        "capas": "Capas",
        "leyenda": "Leyenda",
        "ruta_emergencia": "Ruta de emergencia",
        "mi_ubicacion": "Mi ubicación",
        "pantalla_completa": "Pantalla completa",
        "tipo_hospital": "Hospital",
        "tipo_clinic": "Clínica",
        "tipo_paciente": "Paciente",
        "tipo_ambulancia": "Ambulancia",
        "tipos_hospital": "Hospitales",
        "tipos_clinic": "Clínicas",
        "tipos_paciente": "Pacientes",
        "tipos_ambulancia": "Ambulancias",
    },
    "en": {
        "nodos": "Nodes",
        "aristas": "Edges",
        "paso_origen": "Origin ambulance",
        "paso_destinos": "Destinations",
        "paso_calculo": "Route calculation",
        "sin_asignar": "Unassigned",
        "buscar_destino": "Search hospital, clinic or patient",
        "unidades_disponibles": "units available on the network",
        "destinos_disponibles": "destinations available",
        "destino_seleccionado": "destination selected",
        "destinos_seleccionados": "destinations selected",
        "quitar_destino": "Remove {nombre}",
        "btn_simple": "Single route",
        "btn_multiple": "Multi-stop route",
        "btn_reset": "Reset system",
        "ayuda_simple": "Requires an origin ambulance and at least one destination.",
        "ayuda_multiple": "Requires an origin ambulance and at least two destinations.",
        "hint_simple": "Single:",
        "hint_simple_val": "1 destination",
        "hint_multiple": "Multi-stop:",
        "hint_multiple_val": "2 or more destinations",
        "tiempo_estimado": "estimated time",
        "secuencia": "Sequence",
        "origen": "Origin",
        "parada": "Stop {n}",
        "destinos": "Destinations",
        "paradas": "Stops",
        "err_sin_trayecto": "There is no viable path between those points.",
        "err_afectados": "Affected destinations: {detalle}.",
        "err_y_mas": "and {n} more",
        "aviso_multiples": (
            "{total} destinations were given: the single route only covers the "
            "first one ({destino}). Use Multi-stop route to cover them all."
        ),
        "cargando_titulo": "Preparing the road network",
        "cargando_detalle": "Loading streets, hospitals and units in the district",
        "trazando_mapa": "Drawing map...",
        "err_datos_titulo": "Geographic data could not be loaded",
        "err_datos_ayuda": (
            "The app uses a snapshot bundled in the repository. If it is missing, "
            "regenerate it with: python scripts/build_dataset.py"
        ),
        "capas": "Layers",
        "leyenda": "Legend",
        "ruta_emergencia": "Emergency route",
        "mi_ubicacion": "My location",
        "pantalla_completa": "Fullscreen",
        "tipo_hospital": "Hospital",
        "tipo_clinic": "Clinic",
        "tipo_paciente": "Patient",
        "tipo_ambulancia": "Ambulance",
        "tipos_hospital": "Hospitals",
        "tipos_clinic": "Clinics",
        "tipos_paciente": "Patients",
        "tipos_ambulancia": "Ambulances",
    },
}


def idioma_actual():
    idioma = st.session_state.get("idioma", IDIOMA_POR_DEFECTO)
    return idioma if idioma in TEXTOS else IDIOMA_POR_DEFECTO


def t(clave, **kwargs):
    textos = TEXTOS[idioma_actual()]
    plantilla = textos.get(clave) or TEXTOS[IDIOMA_POR_DEFECTO].get(clave, clave)
    return plantilla.format(**kwargs) if kwargs else plantilla


def etiqueta_tipo(tipo):
    return t(f"tipo_{tipo}")


def plural_tipo(tipo):
    return t(f"tipos_{tipo}")


def nombre_mostrado(entity_id, nombre_guardado):
    """Traduce solo los nombres sinteticos.

    Pacientes y ambulancias se generan con un contador, asi que su nombre se
    reconstruye en el idioma activo. Los hospitales y clinicas vienen de
    OpenStreetMap y conservan su nombre real.
    """
    tipo, separador, numero = str(entity_id).partition(":")
    if separador and tipo in ("paciente", "ambulancia") and numero.isdigit():
        return f"{etiqueta_tipo(tipo)} {numero}"
    return nombre_guardado


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


def _leer_dataset(archivo_grafo, archivo_entidades):
    G = ox.io.load_graphml(archivo_grafo)
    df = pd.read_json(archivo_entidades, orient="table")
    df["node_id"] = df["node_id"].astype("int64")
    _validar_datos(G, df)
    return G, df


def _cargar_snapshot():
    """Datos versionados en data/, sin caducidad.

    Es la unica fuente disponible en despliegues sin salida a Overpass, asi que
    no se le aplica TTL: se regenera a proposito con scripts/build_dataset.py.
    """
    archivos = (DATA_GRAPH_FILE, DATA_ENTITIES_FILE, DATA_MANIFEST_FILE)
    if not all(archivo.exists() for archivo in archivos):
        return None
    try:
        with DATA_MANIFEST_FILE.open("r", encoding="utf-8") as archivo:
            manifiesto = json.load(archivo)
        if manifiesto.get("signature") != _firma_cache():
            LOGGER.warning(
                "El snapshot de data/ no corresponde a la configuracion actual."
            )
            return None
        if manifiesto.get("checksums", {}) != {
            DATA_GRAPH_FILE.name: _sha256(DATA_GRAPH_FILE),
            DATA_ENTITIES_FILE.name: _sha256(DATA_ENTITIES_FILE),
        }:
            raise ValueError("El snapshot no supero la verificacion SHA-256.")
        return _leer_dataset(DATA_GRAPH_FILE, DATA_ENTITIES_FILE)
    except Exception:
        LOGGER.warning("El snapshot de data/ no es utilizable.", exc_info=True)
        return None


def _cargar_cache():
    archivos = (CACHE_GRAPH_FILE, CACHE_ENTITIES_FILE, CACHE_META_FILE)
    if not all(archivo.exists() for archivo in archivos):
        return None
    try:
        with CACHE_META_FILE.open("r", encoding="utf-8") as archivo:
            metadata = json.load(archivo)
        if metadata.get("signature") != _firma_cache():
            return None
        if time.time() - float(metadata["created_at"]) > CACHE_TTL_SECONDS:
            LOGGER.info("El cache geografico expiro y se actualizara.")
            return None
        if metadata.get("checksums", {}) != {
            CACHE_GRAPH_FILE.name: _sha256(CACHE_GRAPH_FILE),
            CACHE_ENTITIES_FILE.name: _sha256(CACHE_ENTITIES_FILE),
        }:
            raise ValueError(
                "Los archivos del cache no superaron la verificacion SHA-256."
            )
        return _leer_dataset(CACHE_GRAPH_FILE, CACHE_ENTITIES_FILE)
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
    for fuente in (_cargar_snapshot, _cargar_cache):
        guardado = fuente()
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

.mk {
  line-height: 0;
  filter: drop-shadow(0 1px 2px rgba(27,36,38,.32));
}
.mk svg { display: block; }

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
  content: 'TITULOCAPAS'; display: block;
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
.hn-leyenda div { display: flex; align-items: center; gap: 9px; }
.hn-leyenda svg { flex: none; }
@media (max-width: 640px) { .hn-leyenda { display: none; } }
</style>
"""


def _rgb(hexadecimal):
    h = hexadecimal.lstrip("#")
    return ",".join(str(int(h[i : i + 2], 16)) for i in (0, 2, 4))


def _css_mapa():
    reemplazos = {
        "TITULOCAPAS": t("capas"),
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


def svg_marca(tipo, tam=12):
    """Icono del tipo de entidad, con la misma forma que en el mapa."""
    color = COLORES[tipo]
    if tipo in ("hospital", "clinic"):
        return (
            f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" '
            'role="img" aria-hidden="true">'
            f'<rect x="1" y="1" width="22" height="22" rx="7" fill="{color}"/>'
            '<path d="M10.3 5.4h3.4v4.9h4.9v3.4h-4.9v4.9h-3.4v-4.9H5.4v-3.4h4.9z" '
            'fill="#fff"/></svg>'
        )
    radio = 9 if tipo == "ambulancia" else 7
    return (
        f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" '
        'role="img" aria-hidden="true">'
        f'<circle cx="12" cy="12" r="{radio}" fill="{color}"/></svg>'
    )


def _svg_insignia(texto, relleno, borde, color_texto, tam):
    return (
        f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" aria-hidden="true">'
        f'<circle cx="12" cy="12" r="10.4" fill="{relleno}" stroke="{borde}" '
        'stroke-width="2"/>'
        f'<text x="12" y="12" text-anchor="middle" dominant-baseline="central" '
        f'font-size="10" font-weight="700" fill="{color_texto}" '
        f'font-family="Merriweather, Georgia, serif">{texto}</text></svg>'
    )


def _svg_linea(color, ancho=16, alto=12):
    return (
        f'<svg width="{ancho}" height="{alto}" viewBox="0 0 16 12" aria-hidden="true">'
        f'<line x1="1" y1="6" x2="15" y2="6" stroke="{color}" stroke-width="2.6" '
        'stroke-linecap="round"/></svg>'
    )


def _icono(svg, tam):
    return folium.DivIcon(
        icon_size=(tam, tam),
        icon_anchor=(tam // 2, tam // 2),
        popup_anchor=(0, -tam // 2 - 2),
        html=f'<div class="mk">{svg}</div>',
    )


def _popup(nombre, tipo, rol=""):
    nombre_seguro = html_lib.escape(str(nombre))
    tipo_seguro = html_lib.escape(etiqueta_tipo(tipo))
    rol_seguro = html_lib.escape(str(rol))
    marca = f'<span class="pop-rol">{rol_seguro}</span>' if rol else ""
    return folium.Popup(
        f'<span class="pop-tipo">{tipo_seguro}</span>'
        f'<span class="pop-nombre">{nombre_seguro}</span>{marca}',
        max_width=250,
    )


def _leyenda():
    filas = "".join(
        f"<div>{svg_marca(tipo, 12)}{html_lib.escape(etiqueta_tipo(tipo))}</div>"
        for tipo in ("hospital", "clinic", "paciente", "ambulancia")
    )
    return (
        f'<div class="hn-leyenda"><b>{html_lib.escape(t("leyenda"))}</b>{filas}'
        f"<div>{_svg_linea(C['ruta'])}"
        f"{html_lib.escape(t('ruta_emergencia'))}</div></div>"
    )


def _nombre_capa(tipo):
    return (
        f'<i class="cap-dot" style="background:{COLORES[tipo]}"></i>'
        f"{html_lib.escape(plural_tipo(tipo))}"
    )


def _capas_entidades(m, df, paradas):
    capas = {t: folium.FeatureGroup(name=_nombre_capa(t), show=True) for t in COLORES}

    for fila in df.itertuples():
        tipo = fila.tipo
        capa = capas.get(tipo)
        if capa is None or fila.entity_id in paradas:
            continue

        coords = (fila.lat, fila.lon)
        nombre = nombre_mostrado(fila.entity_id, fila.nombre)
        popup = _popup(nombre, tipo)

        if tipo in ("hospital", "clinic"):
            folium.Marker(
                coords,
                popup=popup,
                tooltip=html_lib.escape(str(nombre)),
                icon=_icono(svg_marca(tipo, 21), 21),
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
                tooltip=html_lib.escape(str(nombre)),
            ).add_to(capa)

    for capa in capas.values():
        capa.add_to(m)


def _capa_ruta(m, G, ruta, paradas, indice):
    grupo = folium.FeatureGroup(name=t("ruta_emergencia"), show=True, control=False)

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
        nid, nombre_bruto, tipo, lat, lon = indice[entity_id]
        nombre = nombre_mostrado(entity_id, nombre_bruto)
        total_nodo = repeticiones[nid]
        posicion = vistos.get(nid, 0)
        vistos[nid] = posicion + 1
        if total_nodo > 1:
            angulo = 2 * math.pi * posicion / total_nodo
            lat += 0.000025 * math.cos(angulo)
            lon += 0.000025 * math.sin(angulo) / max(math.cos(math.radians(lat)), 0.2)
        if i == 0:
            icono = _icono(_svg_insignia("A", C["ambulancia"], "#fff", "#fff", 24), 24)
            rol = t("origen")
        else:
            icono = _icono(_svg_insignia(str(i), "#fff", C["ruta"], C["ruta"], 23), 23)
            rol = t("parada", n=i)
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

    LocateControl(position="topleft", strings={"title": t("mi_ubicacion")}).add_to(m)
    Fullscreen(position="topleft", title=t("pantalla_completa")).add_to(m)
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
.stApp .hn-cifras {
  display: flex; align-items: center; gap: 18px; margin-right: 128px;
}
@media (max-width: 720px) { .stApp .hn-cifras { margin-right: 104px; } }
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
/* El boton suelto del panel (Resetear) y el selector de idioma necesitan su
   propio aire: son hijos directos, a diferencia del par de botones de calculo,
   que va dentro de un bloque horizontal. */
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:has(.stButton) { padding-top: 24px; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:has([data-testid="stButtonGroup"]) {
  padding-top: 20px;
}

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

/* Un boton con help= va envuelto en stTooltipHoverTarget, no en .stButton, asi
   que se apunta al propio boton por su testid. Se excluye el control de idioma,
   que usa el mismo prefijo pero necesita su tamano compacto. */
.stApp .stButton, .stApp .stButton > button { width: 100%; }
.stApp .stTooltipHoverTarget { width: 100%; }
.stApp button[data-testid^="stBaseButton-"]:not([data-testid*="segmented"]) {
  width: 100%;
  border-radius: 10px !important; font-size: 13px !important; font-weight: 700;
  padding: 12px 12px !important; min-height: 46px !important;
  letter-spacing: .005em;
  border: 1px solid transparent; box-shadow: none !important;
  transition: background .15s ease, border-color .15s ease, color .15s ease;
}
.stApp button[data-testid="stBaseButton-primary"] {
  background: var(--accent) !important; color: #fff !important;
  border-color: var(--accent) !important;
  box-shadow: 0 1px 2px rgba(15,118,110,.22) !important;
}
.stApp button[data-testid="stBaseButton-primary"]:hover {
  background: var(--accent-hover) !important;
  border-color: var(--accent-hover) !important;
}
.stApp button[data-testid="stBaseButton-secondary"] {
  background: var(--surface) !important; color: var(--text) !important;
  border-color: var(--line) !important;
}
.stApp button[data-testid="stBaseButton-secondary"]:hover {
  background: var(--surface-2) !important; border-color: var(--text-3) !important;
}
.stApp button[data-testid^="stBaseButton-"]:disabled,
.stApp button[data-testid^="stBaseButton-"]:disabled:hover {
  background: var(--surface-2) !important; color: var(--text-3) !important;
  border-color: var(--line) !important; opacity: 1 !important; cursor: not-allowed;
}
.stApp button[data-testid^="stBaseButton-"]:focus-visible {
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
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}

.stApp span[data-baseweb="tag"] { display: none !important; }

.stApp .hn-chip {
  display: flex; align-items: center; gap: 10px; min-width: 0;
  padding: 7px 0;
}
.stApp .hn-chip span {
  font-size: 12.5px !important; color: var(--text); min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.hn-chip) {
  padding: 0;
}
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.hn-chip) {
  align-items: center; gap: 4px !important;
}
.stApp button[data-testid="stBaseButton-tertiary"] {
  min-height: 30px !important; padding: 0 !important; width: auto !important; color: var(--text-3) !important;
  font-size: 17px !important; font-weight: 400; background: transparent !important;
  border: none !important;
}
.stApp button[data-testid="stBaseButton-tertiary"]:hover {
  color: var(--ruta) !important; background: var(--surface-2) !important;
}

/* El selector de idioma se ancla a la barra superior: es un ajuste global y
   ahi convive con las cifras de la red. Streamlit no permite widgets dentro de
   HTML propio, asi que se renderiza en el area principal y se fija por CSS. */
[data-testid="stMain"]
  [data-testid="stElementContainer"]:has([data-testid="stButtonGroup"]) {
  position: fixed; top: 0; height: var(--nav-h);
  right: clamp(20px, 7vw, 150px);
  display: flex; align-items: center;
  z-index: 1000002; padding: 0 !important; width: auto !important;
}
.stApp [data-testid="stButtonGroup"] {
  display: flex !important; gap: 8px !important; background: transparent !important;
  border: none !important; padding: 0 !important;
}
/* Los botones cuelgan de un div interno, no del grupo: el gap va ahi. */
.stApp [data-testid="stButtonGroup"] > * { margin: 0 !important; }
.stApp [data-testid="stButtonGroup"] > div {
  display: flex !important; gap: 8px !important;
}
.stApp [data-testid="stButtonGroup"] button {
  font-size: 11px !important; font-weight: 700; letter-spacing: .08em;
  padding: 5px 13px !important; min-height: 28px !important;
  width: auto !important; border-radius: 8px !important;
  margin: 0 !important; border: 1px solid var(--nav-sep) !important;
  background: var(--surface) !important; color: var(--nav-label) !important;
}
.stApp [data-testid="stButtonGroup"] button:hover {
  border-color: var(--accent) !important; color: var(--accent) !important;
}
.stApp button[data-testid="stBaseButton-segmented_controlActive"] {
  background: var(--accent) !important; color: #fff !important;
  border-color: var(--accent) !important;
}

.hn-carga {
  position: fixed; inset: 0; z-index: 2000000;
  background: var(--bg);
  display: flex; align-items: center; justify-content: center;
}
.hn-carga-caja { text-align: center; max-width: 340px; padding: 0 24px; }
.hn-carga-caja img {
  width: 56px; height: 56px; object-fit: contain; margin: 0 auto 16px auto;
  display: block;
}
.hn-carga-marca {
  font-size: 24px !important; font-weight: 900; color: var(--nav-marca);
  line-height: 1; margin-bottom: 22px;
}
.hn-carga-tit {
  font-size: 13px !important; font-weight: 700; color: var(--text);
  margin-bottom: 6px;
}
.hn-carga-det {
  font-size: 11.5px !important; color: var(--text-3); font-weight: 300;
  line-height: 1.55; margin-bottom: 20px;
}
.hn-carga-barra {
  height: 3px; border-radius: 3px; background: var(--line);
  overflow: hidden; position: relative;
}
.hn-carga-barra span {
  position: absolute; inset: 0 auto 0 0; width: 40%;
  border-radius: 3px; background: var(--accent);
  animation: hn-desliz 1.15s ease-in-out infinite;
}
@keyframes hn-desliz {
  0% { left: -40%; } 100% { left: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .hn-carga-barra span { animation: none; left: 0; width: 100%; opacity: .55; }
}

.stApp .hn-fallo {
  max-width: 560px; margin: 12vh auto 0 auto; padding: 24px 26px;
  border: 1px solid var(--line); border-top: 3px solid var(--ruta);
  border-radius: 12px; background: var(--surface);
}
.stApp .hn-fallo h1 {
  font-size: 16px !important; font-weight: 700; color: var(--text);
  margin: 0 0 10px 0;
}
.stApp .hn-fallo p {
  font-size: 12.5px !important; color: var(--text-2); line-height: 1.6;
  margin: 0 0 10px 0;
}
.stApp .hn-fallo code {
  display: block; margin-top: 12px; padding: 10px 12px; border-radius: 8px;
  background: var(--surface-2); color: var(--text-3);
  font-size: 11px !important; overflow-x: auto; white-space: pre-wrap;
}

.stApp [data-testid="stIFrame"],
.stApp [data-testid="stCustomComponentV1"],
.stApp iframe[title="st.iframe"] {
  width: 100% !important;
  height: calc(100vh - var(--nav-h)) !important;
  min-height: 320px;
  border: none !important; display: block;
}
.stApp [data-testid="stElementContainer"]:has(iframe[title="st.iframe"]) {
  height: calc(100vh - var(--nav-h)) !important;
}

/* Con destinos elegidos, baseweb deja de pintar el placeholder (sus etiquetas
   estan ocultas) y el buscador parecia una caja vacia. Se repone por CSS. */
.stApp div[data-baseweb="select"] > div { position: relative; }
.stApp div[data-baseweb="select"]:has(span[data-baseweb="tag"]):not(:focus-within)
  > div::after {
  content: var(--ph-destinos);
  position: absolute; left: 15px; top: 50%; transform: translateY(-50%);
  color: var(--text-3); font-size: 13px; pointer-events: none;
  white-space: nowrap; overflow: hidden; max-width: calc(100% - 70px);
}

section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.hn-chip) {
  border-radius: 8px; transition: background .12s ease;
}
section[data-testid="stSidebar"]
  [data-testid="stHorizontalBlock"]:has(.hn-chip):hover {
  background: var(--surface-2);
}
.stApp .hn-chip { padding: 7px 0 7px 8px; }

/* Los dos botones de calculo forman un par: el activo va relleno y el otro
   apagado, para que se lea cual esta seleccionado. */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
  button[data-testid="stBaseButton-secondary"] {
  background: var(--surface-2) !important;
  color: var(--text-2) !important;
  border-color: var(--line) !important;
}
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
  button[data-testid="stBaseButton-secondary"]:hover {
  background: var(--surface) !important;
  color: var(--text) !important;
  border-color: var(--text-3) !important;
}
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:not(:has(.hn-chip)) {
  gap: 14px !important;
}
"""


def aplicar_estilos():
    variables = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in C.items())
    variables += f';--ph-destinos:"{t("buscar_destino")}"'
    st.markdown(
        f"<style>{_FUENTES}:root{{{variables}}}{_CSS_APP}</style>",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def logo_base64():
    try:
        return base64.b64encode(LOGO_PATH.read_bytes()).decode()
    except OSError:
        return None


def _img_logo(logo, clase=""):
    if not logo:
        return ""
    atributo = f' class="{clase}"' if clase else ""
    return f'<img{atributo} src="data:image/png;base64,{logo}" alt="">'


def pantalla_carga(logo):
    return (
        '<div class="hn-carga"><div class="hn-carga-caja">'
        f"{_img_logo(logo)}"
        '<div class="hn-carga-marca">HealthNet</div>'
        f'<div class="hn-carga-tit">{html_lib.escape(t("cargando_titulo"))}</div>'
        f'<div class="hn-carga-det">{html_lib.escape(t("cargando_detalle"))}</div>'
        '<div class="hn-carga-barra"><span></span></div>'
        "</div></div>"
    )


def pantalla_fallo(detalle):
    st.markdown(
        '<div class="hn-fallo">'
        f"<h1>{html_lib.escape(t('err_datos_titulo'))}</h1>"
        f"<p>{html_lib.escape(t('err_datos_ayuda'))}</p>"
        f"<code>{html_lib.escape(str(detalle))}</code></div>",
        unsafe_allow_html=True,
    )


def barra_superior(logo, n_nodos, n_aristas):
    st.markdown(
        f"""
        <div class="hn-top">
          <div class="hn-brand">
            {_img_logo(logo)}
            <span class="hn-rule"></span>
            <span class="hn-word">HealthNet</span>
          </div>
          <div class="hn-cifras">
            <dl class="hn-cifra"><dt>{html_lib.escape(t("nodos"))}</dt>
              <dd>{n_nodos}</dd></dl>
            <span class="hn-rule"></span>
            <dl class="hn-cifra"><dt>{html_lib.escape(t("aristas"))}</dt>
              <dd>{n_aristas}</dd></dl>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def paso(numero, titulo):
    st.markdown(
        f'<div class="hn-paso"><b>{html_lib.escape(str(numero))}</b><i>\u00b7</i>'
        f"{html_lib.escape(str(titulo))}</div>",
        unsafe_allow_html=True,
    )


def nota(cantidad, texto):
    st.markdown(
        f'<div class="hn-nota"><b>{html_lib.escape(str(cantidad))}</b> '
        f"{html_lib.escape(str(texto))}</div>",
        unsafe_allow_html=True,
    )


def ficha_ruta(tiempo, pares, secuencia=None):
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
            rol = t("origen") if i == 0 else t("parada", n=i)
            cuerpo += (
                f"<div class='{clase}'><b>{marca}</b>"
                f"<span>{html_lib.escape(str(nombre))}</span>"
                f"<em>{html_lib.escape(rol)}</em></div>"
            )
        filas = (
            f"<div class='hn-sec'><div class='hn-sec-tit'>"
            f"{html_lib.escape(t('secuencia'))}</div>{cuerpo}</div>"
        )

    st.markdown(
        "<div class='hn-ficha'>"
        f"<div class='hn-reloj'><strong>{html_lib.escape(str(tiempo))}</strong>"
        f"<span>{html_lib.escape(t('tiempo_estimado'))}</span></div>"
        f"<div class='hn-pares'>{celdas}</div>{filas}</div>",
        unsafe_allow_html=True,
    )


def formatear_tiempo(segundos):
    minutos, resto = divmod(int(segundos), 60)
    if minutos >= 60:
        horas, minutos = divmod(minutos, 60)
        return f"{horas}h {minutos:02d}m"
    return f"{minutos}m {resto:02d}s"


RUTA_VACIA = {
    "tipo": "base",
    "nodos": None,
    "tiempo": None,
    "orden": None,
    "paradas_ids": None,
}


def estado_inicial():
    st.session_state.setdefault("ruta", dict(RUTA_VACIA))
    st.session_state.setdefault("mapa", None)
    st.session_state.setdefault("aviso", "")
    st.session_state.setdefault("idioma", IDIOMA_POR_DEFECTO)
    st.session_state.setdefault("origen_id", SIN_ASIGNAR)
    st.session_state.setdefault("destinos_ids", [])


def resetear():
    st.session_state["ruta"] = dict(RUTA_VACIA)
    st.session_state["aviso"] = ""
    st.session_state["mapa"] = None
    st.session_state["origen_id"] = SIN_ASIGNAR
    st.session_state["destinos_ids"] = []


def quitar_destino(entity_id):
    seleccion = [d for d in st.session_state.get("destinos_ids", []) if d != entity_id]
    st.session_state["destinos_ids"] = seleccion
    st.session_state["ruta"] = dict(RUTA_VACIA)
    st.session_state["aviso"] = ""
    st.session_state["mapa"] = None


def cambiar_idioma():
    """Traduce el mapa y preserva lo que el usuario ya habia elegido.

    Streamlit deriva la identidad de un widget de sus parametros, etiqueta y
    placeholder incluidos. Al traducirlos, el selector pasa a ser un widget
    distinto y nace vacio, asi que su valor se guarda aqui (el callback corre
    antes del rerun) y se resiembra antes de volver a crearlos.
    """
    st.session_state["mapa"] = None
    st.session_state["traspaso"] = {
        "origen_id": st.session_state.get("origen_id", SIN_ASIGNAR),
        "destinos_ids": list(st.session_state.get("destinos_ids", [])),
    }


def _resembrar_seleccion():
    traspaso = st.session_state.pop("traspaso", None)
    if traspaso:
        st.session_state.update(traspaso)


def chips_destinos(ids, tipo_entidad, nombre_entidad):
    """Destinos elegidos, con el icono del tipo y un boton para quitarlos.

    Sustituye a las etiquetas nativas del multiselect (ocultas por CSS), que no
    admiten un icono por elemento.
    """
    for entity_id in ids:
        nombre = nombre_entidad[entity_id]
        columna_chip, columna_quitar = st.columns([0.86, 0.14], gap="small")
        columna_chip.markdown(
            f"<div class='hn-chip'>{svg_marca(tipo_entidad[entity_id], 13)}"
            f"<span>{html_lib.escape(str(nombre))}</span></div>",
            unsafe_allow_html=True,
        )
        columna_quitar.button(
            "\u00d7",
            key=f"quitar_{entity_id}",
            type="tertiary",
            help=t("quitar_destino", nombre=nombre),
            on_click=quitar_destino,
            args=(entity_id,),
        )


def main():
    st.set_page_config(
        page_title="HealthNet",
        page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "+",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    aplicar_estilos()
    estado_inicial()

    logo = logo_base64()
    velo = st.empty()
    velo.markdown(pantalla_carga(logo), unsafe_allow_html=True)
    try:
        G, nodos_df = cargar_datos()
    except Exception as exc:  # noqa: BLE001
        velo.empty()
        pantalla_fallo(exc)
        st.stop()
    velo.empty()

    barra_superior(logo, G.number_of_nodes(), G.number_of_edges())
    st.segmented_control(
        "idioma",
        options=IDIOMAS,
        format_func=str.upper,
        key="idioma",
        label_visibility="collapsed",
        on_change=cambiar_idioma,
    )

    entidades = nodos_df.set_index("entity_id", drop=False)
    nombre_entidad = {
        entity_id: nombre_mostrado(entity_id, nombre)
        for entity_id, nombre in entidades["nombre"].items()
    }
    nodo_entidad = entidades["node_id"].astype("int64").to_dict()
    tipo_entidad = entidades["tipo"].to_dict()

    def por_nombre(entity_id):
        return len(nombre_entidad[entity_id]), nombre_entidad[entity_id], entity_id

    ambulancias = sorted(
        nodos_df.loc[nodos_df["tipo"] == "ambulancia", "entity_id"], key=por_nombre
    )
    destinos_disponibles = sorted(
        nodos_df.loc[nodos_df["tipo"].isin(TIPOS_DESTINO), "entity_id"], key=por_nombre
    )

    _resembrar_seleccion()

    with st.sidebar:
        paso("01", t("paso_origen"))
        origen_id = st.selectbox(
            t("paso_origen"),
            options=[SIN_ASIGNAR] + ambulancias,
            format_func=lambda eid: (
                t("sin_asignar") if eid == SIN_ASIGNAR else nombre_entidad[eid]
            ),
            label_visibility="collapsed",
            key="origen_id",
        )
        nota(len(ambulancias), t("unidades_disponibles"))

        paso("02", t("paso_destinos"))
        destinos_sel = st.multiselect(
            t("paso_destinos"),
            options=destinos_disponibles,
            format_func=lambda eid: nombre_entidad[eid],
            placeholder=t("buscar_destino"),
            label_visibility="collapsed",
            key="destinos_ids",
        )
        if destinos_sel:
            chips_destinos(destinos_sel, tipo_entidad, nombre_entidad)
            nota(
                len(destinos_sel),
                t(
                    "destino_seleccionado"
                    if len(destinos_sel) == 1
                    else "destinos_seleccionados"
                ),
            )
        else:
            nota(len(destinos_disponibles), t("destinos_disponibles"))

        paso("03", t("paso_calculo"))
        hay_origen = origen_id != SIN_ASIGNAR
        modo = st.session_state["ruta"]["tipo"]
        columna_a, columna_b = st.columns(2, gap="small")
        btn_simple = columna_a.button(
            t("btn_simple"),
            key="btn_simple",
            type="primary" if modo == "simple" else "secondary",
            width="stretch",
            disabled=not (hay_origen and destinos_sel),
            help=t("ayuda_simple"),
        )
        btn_multiple = columna_b.button(
            t("btn_multiple"),
            key="btn_multiple",
            type="primary" if modo == "multiple" else "secondary",
            width="stretch",
            disabled=not (hay_origen and len(destinos_sel) >= 2),
            help=t("ayuda_multiple"),
        )
        st.markdown(
            f"<div class='hn-algo'><b>{html_lib.escape(t('hint_simple'))}</b> "
            f"{html_lib.escape(t('hint_simple_val'))}<br>"
            f"<b>{html_lib.escape(t('hint_multiple'))}</b> "
            f"{html_lib.escape(t('hint_multiple_val'))}</div>",
            unsafe_allow_html=True,
        )

        if btn_simple and destinos_sel:
            destino_id = destinos_sel[0]
            src = int(nodo_entidad[origen_id])
            dst = int(nodo_entidad[destino_id])
            nodos, tiempo = calcular_ruta_optima(G, src, dst)
            if nodos is None:
                st.error(t("err_sin_trayecto"))
            else:
                st.session_state["aviso"] = (
                    t(
                        "aviso_multiples",
                        total=len(destinos_sel),
                        destino=nombre_entidad[destino_id],
                    )
                    if len(destinos_sel) > 1
                    else ""
                )
                st.session_state["ruta"] = {
                    "tipo": "simple",
                    "nodos": nodos,
                    "tiempo": tiempo,
                    "orden": [src, dst],
                    "paradas_ids": [origen_id, destino_id],
                }
                st.session_state["mapa"] = None
                st.rerun()

        if btn_multiple and len(destinos_sel) >= 2:
            src = int(nodo_entidad[origen_id])
            objetivos = [int(nodo_entidad[eid]) for eid in destinos_sel]
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
                    detalle += " " + t("err_y_mas", n=len(afectados) - 5)
                st.session_state["ruta"] = dict(RUTA_VACIA)
                st.session_state["mapa"] = None
                st.error(
                    resultado["error"]
                    + (" " + t("err_afectados", detalle=detalle) if detalle else "")
                )

        estado = st.session_state["ruta"]
        if estado["tipo"] == "simple":
            ficha_ruta(
                formatear_tiempo(estado["tiempo"]),
                [(t("destinos"), "1")],
                secuencia=[nombre_entidad[eid] for eid in estado["paradas_ids"]],
            )
        elif estado["tipo"] == "multiple":
            ficha_ruta(
                formatear_tiempo(estado["tiempo"]),
                [(t("paradas"), f"{max(len(estado['orden']) - 1, 0)}")],
                secuencia=[nombre_entidad[eid] for eid in estado["paradas_ids"]],
            )

        if st.session_state["aviso"]:
            st.warning(st.session_state["aviso"])

        st.button(
            t("btn_reset"),
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

    if st.session_state["mapa"] is None:
        with st.spinner(t("trazando_mapa")):
            if estado["tipo"] == "base":
                clave = json.dumps(
                    {**_firma_cache(), "idioma": idioma_actual()}, sort_keys=True
                )
                st.session_state["mapa"] = mapa_base(G, nodos_df, clave)
            else:
                st.session_state["mapa"] = generar_mapa(
                    G, nodos_df, estado["nodos"], estado["paradas_ids"]
                )

    html(st.session_state["mapa"], height=760, scrolling=False)


if __name__ == "__main__":
    main()
