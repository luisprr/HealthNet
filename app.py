import os
import random
import folium
import networkx as nx
import osmnx as ox
import pandas as pd
import streamlit as st
from folium.plugins import Fullscreen, LocateControl, MarkerCluster
from streamlit.components.v1 import html
from PIL import Image
import base64


PLACE_NAME = "Ciudad Autónoma de Buenos Aires, Argentina"
POI_TAGS = {"amenity": ["hospital", "clinic"]}

COLORES = {
    "hospital": "#e63946",
    "clinic": "#a06cd5",
    "paciente": "#457b9d",
    "ambulancia": "#2a9d8f",
}

LOGO_PATH = r"HealthNetLogo.png"

def get_logo_base64():
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception as e:
        print(f"No se pudo cargar el logo: {e}")
        return None

def cargar_y_procesar_datos(lugar):
    print(f"🏥 Cargando red vial de {lugar}...")
    ox.settings.use_cache = True
    ox.settings.log_console = False

    G = ox.graph_from_place(
        lugar,
        network_type="drive",
        custom_filter='["highway"~"primary|secondary|tertiary|residential|unclassified"]',
    )
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    print(f"✓ Grafo: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas")

    try:
        pois_gdf = ox.features.features_from_place(lugar, POI_TAGS)
        print(f"✓ POIs obtenidos: {len(pois_gdf)}")
    except Exception as e:
        print(f"⚠ No se pudieron obtener POIs: {e}")
        pois_gdf = pd.DataFrame()

    nodes = []

    if not pois_gdf.empty:
        pois_gdf = pois_gdf[pois_gdf.geometry.notna()]
        for _, poi in pois_gdf.iterrows():
            geom = poi.geometry.centroid
            tipo = poi.get("amenity") or "hospital"
            nombre = (
                poi.get("name")
                if isinstance(poi.get("name"), str)
                else f"{tipo.capitalize()} sin nombre"
            )
            nodes.append(
                {
                    "lat": geom.y,
                    "lon": geom.x,
                    "tipo": tipo,
                    "nombre": nombre,
                }
            )

    posibles = list(G.nodes())

    print("🧍 Generando 200 pacientes...")
    for i, n in enumerate(random.sample(posibles, min(200, len(posibles)))):
        nodo = G.nodes[n]
        nodes.append(
            {
                "lat": nodo["y"],
                "lon": nodo["x"],
                "tipo": "paciente",
                "nombre": f"Paciente {i+1}",
            }
        )

    print("🚑 Generando 40 ambulancias...")
    for j, n in enumerate(random.sample(posibles, min(40, len(posibles)))):
        nodo = G.nodes[n]
        nodes.append(
            {
                "lat": nodo["y"],
                "lon": nodo["x"],
                "tipo": "ambulancia",
                "nombre": f"Ambulancia {j+1}",
            }
        )

    nodos_df = pd.DataFrame(nodes)

    node_ids = ox.nearest_nodes(G, X=nodos_df["lon"], Y=nodos_df["lat"])
    nodos_df["node_id"] = node_ids

    for _, row in nodos_df.iterrows():
        G.nodes[row["node_id"]].update(
            {
                "custom_poi": True,
                "tipo": row["tipo"],
                "nombre": row["nombre"],
            }
        )

    print("✓ Datos procesados correctamente\n")
    return G, nodos_df


def calcular_ruta_optima(G, src_node, dst_node):
    try:
        ruta = nx.dijkstra_path(G, src_node, dst_node, weight="travel_time")
        tiempo = nx.path_weight(G, ruta, weight="travel_time")
        return ruta, tiempo
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None, None


def two_opt(route, G):
    if len(route) <= 2:
        return route

    best = route[:]
    improved = True

    try:
        old_time = sum(
            nx.dijkstra_path_length(G, a, b, weight="travel_time")
            for a, b in zip(best[:-1], best[1:])
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return route

    while improved:
        improved = False
        for i in range(1, len(best) - 1):
            for k in range(i + 1, len(best)):
                new_route = best[:i] + best[i: k + 1][::-1] + best[k + 1:]

                try:
                    new_time = sum(
                        nx.dijkstra_path_length(G, a, b, weight="travel_time")
                        for a, b in zip(new_route[:-1], new_route[1:])
                    )
                    if new_time < old_time:
                        best = new_route
                        old_time = new_time
                        improved = True
                        break
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
            if improved:
                break

    return best


def calcular_ruta_tsp(G, nodo_origen, nodos_destino):
    pendientes = list(nodos_destino)
    orden = [nodo_origen]
    actual = nodo_origen

    while pendientes:
        siguiente, tiempo_min = None, float("inf")
        for dest in pendientes:
            try:
                t = nx.dijkstra_path_length(G, actual, dest, weight="travel_time")
                if t < tiempo_min:
                    siguiente, tiempo_min = dest, t
            except nx.NetworkXNoPath:
                continue

        if siguiente is None:
            break

        orden.append(siguiente)
        pendientes.remove(siguiente)
        actual = siguiente

    if len(orden) <= 2:
        orden_opt = orden
    else:
        orden_opt = two_opt(orden, G)

    ruta_completa, tiempo_total = [], 0
    for i in range(len(orden_opt) - 1):
        seg, t = calcular_ruta_optima(G, orden_opt[i], orden_opt[i + 1])
        if seg:
            ruta_completa.extend(seg if i == 0 else seg[1:])
            tiempo_total += t

    return ruta_completa, tiempo_total, orden_opt


def _inject_fonts(m):
    css = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700;900&display=swap');
      html, body, .leaflet-container, .leaflet-popup-content, .leaflet-control {
        font-family: 'Merriweather', Georgia, serif !important;
      }
      .leaflet-popup-content {
        font-size: 14px;
        line-height: 1.7;
      }
      .leaflet-popup-content-wrapper {
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.2);
      }
      .leaflet-control-layers-expanded {
        font-size: 13px;
        border-radius: 8px;
      }
    </style>
    """
    m.get_root().html.add_child(folium.Element(css))


def generar_mapa_con_ruta(
    G, df, ruta=None, nombre_html="mapa_emergencia.html", ruta_ordenada=None
):
    center = [df["lat"].mean(), df["lon"].mean()]
    m = folium.Map(location=center, zoom_start=13, tiles=None, control_scale=True)

    folium.TileLayer("cartodbdark_matter", name="Base oscura", control=False).add_to(m)

    edges = ox.graph_to_gdfs(G, nodes=False)
    folium.GeoJson(
        edges,
        style_function=lambda _: {"color": "#334155", "weight": 2.2, "opacity": 0.7},
        overlay=True,
        control=False,
    ).add_to(m)

    folium.GeoJson(
        edges,
        name="Red vial",
        style_function=lambda _: {"color": "#475569", "weight": 1.0, "opacity": 0.9},
        overlay=True,
        control=True,
    ).add_to(m)

    if ruta and len(ruta) > 1:
        try:
            ruta_gdf = ox.routing.route_to_gdf(G, ruta)
            folium.GeoJson(
                ruta_gdf,
                name="Ruta de Emergencia",
                style_function=lambda _: {
                    "color": "#dc2626",
                    "weight": 6,
                    "opacity": 0.95,
                    "lineJoin": "round",
                },
                tooltip="Ruta calculada",
            ).add_to(m)
        except Exception as e:
            print(f"⚠ Error al dibujar ruta: {e}")

    paradas = {}
    if ruta_ordenada:
        for i, nid in enumerate(ruta_ordenada):
            paradas[nid] = "ORIGEN" if i == 0 else f"PARADA {i}"

    capa_hosp = folium.FeatureGroup(name="Hospitales", show=True)
    capa_clin = folium.FeatureGroup(name="Clínicas", show=True)
    capa_pac = folium.FeatureGroup(name="Pacientes", show=True)
    capa_amb = folium.FeatureGroup(name="Ambulancias", show=True)

    cluster_hosp = MarkerCluster(name="Cluster Hospitales")
    cluster_clin = MarkerCluster(name="Cluster Clínicas")

    for _, row in df.iterrows():
        tipo = row["tipo"]
        color = COLORES.get(tipo, "gray")

        es_parada = bool(row.get("es_parada", False)) and row["node_id"] in paradas
        info_parada = paradas[row["node_id"]] if es_parada else ""

        popup_text = (
            f"<b style='color:#dc2626; font-size:14px; text-transform:uppercase;'>{info_parada}</b><br>"
            if info_parada
            else ""
        )
        popup_text += f"<b>{row['nombre']}</b><br><small style='text-transform:uppercase;'>({row['tipo']})</small>"
        popup = folium.Popup(popup_text, max_width=280)

        if tipo == "hospital":
            if es_parada:
                folium.Marker(
                    [row["lat"], row["lon"]],
                    popup=popup,
                    icon=folium.Icon(color="red", icon="star", prefix="fa"),
                    tooltip=info_parada,
                ).add_to(capa_hosp)
            else:
                folium.Marker(
                    [row["lat"], row["lon"]],
                    popup=popup,
                    icon=folium.Icon(color="red", icon="plus", prefix="fa"),
                ).add_to(cluster_hosp)
        elif tipo == "clinic":
            if es_parada:
                folium.Marker(
                    [row["lat"], row["lon"]],
                    popup=popup,
                    icon=folium.Icon(color="purple", icon="star", prefix="fa"),
                    tooltip=info_parada,
                ).add_to(capa_clin)
            else:
                folium.Marker(
                    [row["lat"], row["lon"]],
                    popup=popup,
                    icon=folium.Icon(color="purple", icon="plus", prefix="fa"),
                ).add_to(cluster_clin)
        elif tipo == "paciente":
            if es_parada:
                folium.Marker(
                    [row["lat"], row["lon"]],
                    popup=popup,
                    icon=folium.Icon(
                        color="orange", icon="star", prefix="fa", icon_color="white"
                    ),
                    tooltip=info_parada,
                ).add_to(capa_pac)
            else:
                folium.CircleMarker(
                    [row["lat"], row["lon"]],
                    radius=4,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.7,
                    weight=1,
                    popup=popup,
                ).add_to(capa_pac)
        elif tipo == "ambulancia":
            if es_parada:
                folium.Marker(
                    [row["lat"], row["lon"]],
                    popup=popup,
                    icon=folium.Icon(
                        color="green",
                        icon="flag-checkered",
                        prefix="fa",
                        icon_color="white",
                    ),
                    tooltip=info_parada,
                ).add_to(capa_amb)
            else:
                folium.CircleMarker(
                    [row["lat"], row["lon"]],
                    radius=6,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.85,
                    weight=1,
                    popup=popup,
                ).add_to(capa_amb)

    cluster_hosp.add_to(capa_hosp)
    cluster_clin.add_to(capa_clin)

    for capa in [capa_hosp, capa_clin, capa_pac, capa_amb]:
        capa.add_to(m)

    Fullscreen(position="topleft").add_to(m)
    LocateControl(position="topleft").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    legend = f"""
    <div style="position: fixed; bottom: 20px; right: 20px; z-index: 9999;
      background: rgba(15,23,42,0.96); border-radius: 8px;
      padding: 16px 20px; font-size: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4); backdrop-filter: blur(10px);
      border: 1px solid rgba(148, 163, 184, 0.1);
      color: #e5e7eb; font-family: 'Merriweather', Georgia, serif;">
      <b style="font-size:14px; margin-bottom:12px; display:block; color:#f1f5f9; text-transform:uppercase; letter-spacing:1px;">Leyenda</b>
      <div style="line-height: 2;">
        <i style="background:{COLORES['hospital']}; width:12px; height:12px; border-radius:50%; display:inline-block; margin-right:10px;"></i> Hospital<br>
        <i style="background:{COLORES['clinic']}; width:12px; height:12px; border-radius:50%; display:inline-block; margin-right:10px;"></i> Clínica<br>
        <i style="background:{COLORES['paciente']}; width:12px; height:12px; border-radius:50%; display:inline-block; margin-right:10px;"></i> Paciente<br>
        <i style="background:{COLORES['ambulancia']}; width:12px; height:12px; border-radius:50%; display:inline-block; margin-right:10px;"></i> Ambulancia
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    _inject_fonts(m)
    m.save(nombre_html)
    return os.path.abspath(nombre_html)

@st.cache_resource
def load_data_cached():
    return cargar_y_procesar_datos(PLACE_NAME)


def init_session_state():
    if "map_state" not in st.session_state:
        st.session_state["map_state"] = {
            "tipo_ruta": "base",
            "ruta": None,
            "tiempo": None,
            "orden": None,
            "nombres_paradas": None,
        }
    if "map_html" not in st.session_state:
        st.session_state["map_html"] = None
    if "show_warning" not in st.session_state:
        st.session_state["show_warning"] = False
    if "warning_message" not in st.session_state:
        st.session_state["warning_message"] = ""


def apply_custom_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700;900&family=Lato:wght@300;400;700&display=swap');

        * {
            font-family: 'Lato', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Merriweather', Georgia, serif !important;
        }

        /* Fondo principal app */
        .stApp {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
            padding-top: 64px !important;  /* altura navbar */
        }

        /* === NAVBAR ESTILO IMAGEN === */
        .navbar {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 64px;
            background: #ffffff;
            border-bottom: 1px solid #e5e7eb;
            box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
            z-index: 999999;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 180px;
        }

        .navbar-logo-section {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .navbar-logo {
            width: 40px;
            height: 40px;
            object-fit: contain;
        }

        .navbar-text-block {
            display: flex;
            flex-direction: column;
            justify-content: center;
        }

        .navbar-title {
            font-size: 22px;
            font-weight: 800;
            margin: 0;
            letter-spacing: 0.3px;
            font-family: 'Merriweather', Georgia, serif;
            color: #0f766e;
        }

        .navbar-subtitle {
            display: none;
        }

        .navbar-right {
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 11px;
            color: #6b7280;
            font-weight: 500;
            white-space: nowrap;
        }

        .navbar-metric-label {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 10px;
            color: #6b7280;
        }

        .navbar-metric-value {
            font-size: 14px;
            font-weight: 800;
            color: #0f766e;
            margin-left: 4px;
        }

        .navbar-separator {
            color: #d1d5db;
            margin: 0 12px;
        }

        /* Sidebar ancho */
        section[data-testid="stSidebar"] {
            top: 64px !important;
            height: calc(100vh - 64px) !important;
            width: 400px !important;
            min-width: 400px !important;
            max-width: 400px !important;
            background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
            border-right: 1px solid rgba(94, 234, 212, 0.25);
            box-shadow: 4px 0 24px rgba(15, 23, 42, 0.8);
        }

        section[data-testid="stSidebar"] > div {
            background: transparent;
            padding-top: 8px !important; 
        }

        section[data-testid="stSidebar"] * {
            color: #f0fdfa !important;
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: #f1f5f9 !important;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }

        /* Quitar anchors en headings */
        h1 a, h2 a, h3 a, [data-testid="stHeading"] a {
            display: none !important;
            pointer-events: none !important;
        }

        /* Selects / multiselects */
        .stSelectbox > div > div,
        .stMultiSelect > div > div {
            background: rgba(15, 23, 42, 0.8) !important;
            border: 1px solid rgba(94, 234, 212, 0.3);
            border-radius: 6px;
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
        }

        .stSelectbox > div > div:hover,
        .stMultiSelect > div > div:hover {
            border-color: #0d9488;
            box-shadow: 0 0 0 2px rgba(94, 234, 212, 0.25);
        }

        .stSelectbox input,
        .stMultiSelect input {
            color: #f1f5f9 !important;
        }

        div[role="listbox"] {
            background: rgba(15, 23, 42, 0.98) !important;
            border: 1px solid rgba(94, 234, 212, 0.35) !important;
            border-radius: 6px;
            backdrop-filter: blur(10px);
        }

        div[role="option"] {
            background: transparent !important;
            color: #e2e8f0 !important;
            transition: all 0.2s ease;
        }

        div[role="option"]:hover {
            background: rgba(13, 148, 136, 0.15) !important;
            color: #5eead4 !important;
        }

        .stButton > button {
            width: 100%;
            background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 12px 20px;
            font-weight: 600;
            font-size: 13px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 12px rgba(13, 148, 136, 0.4);
        }

        .stButton > button:hover {
            background: linear-gradient(135deg, #0f766e 0%, #0d9488 100%);
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(13, 148, 136, 0.55);
        }

        .stButton > button:active {
            transform: translateY(0);
        }

        .stAlert {
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 8px;
            backdrop-filter: blur(10px);
            padding: 16px;
            animation: slideIn 0.3s ease;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .stSuccess {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%) !important;
            border-left: 4px solid #10b981 !important;
        }

        .stError {
            background: linear-gradient(135deg, rgba(220, 38, 38, 0.15) 0%, rgba(220, 38, 38, 0.05) 100%) !important;
            border-left: 4px solid #dc2626 !important;
        }

        .stInfo {
            background: linear-gradient(135deg, rgba(13, 148, 136, 0.15) 0%, rgba(13, 148, 136, 0.05) 100%) !important;
            border-left: 4px solid #0d9488 !important;
        }

        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        ::-webkit-scrollbar-track {
            background: rgba(15, 23, 42, 0.8);
        }

        ::-webkit-scrollbar-thumb {
            background: linear-gradient(180deg, #0d9488 0%, #0f766e 100%);
            border-radius: 5px;
            border: 2px solid transparent;
            background-clip: padding-box;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: linear-gradient(180deg, #0f766e 0%, #0d9488 100%);
            background-clip: padding-box;
        }

        span[data-baseweb="tag"] {
            background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%) !important;
            color: #ffffff !important;
            border-radius: 4px;
            padding: 4px 10px;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }

        hr {
            border-color: rgba(94, 234, 212, 0.25) !important;
            margin: 16px 0 !important;
        }

        .main .block-container {
            padding-top: 1rem;   /* <<< antes 2rem: sube Vista Base Activa y la tarjeta de rutas */
            padding-bottom: 2rem;
        }

        .glass-card {
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(94, 234, 212, 0.25);
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(15, 23, 42, 0.9);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    try:
        logo_img = Image.open(LOGO_PATH)
        st.set_page_config(
            page_title="HealthNet",
            layout="wide",
            page_icon=logo_img,
            initial_sidebar_state="expanded",
        )
    except:
        st.set_page_config(
            page_title="HealthNet",
            layout="wide",
            page_icon="🏥",
            initial_sidebar_state="expanded",
        )

    apply_custom_css()
    init_session_state()

    if "data_loaded" not in st.session_state:
        logo_b64 = get_logo_base64()
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" style="width:120px; height:120px; object-fit:contain; filter: drop-shadow(0 8px 24px rgba(13, 148, 136, 0.5));">'
            if logo_b64
            else '<div style="font-size: 96px;">+</div>'
        )

        st.markdown(
            f"""
            <style>
            @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700;900&family=Lato:wght@300;400;700&display=swap');
            .loading-container {{
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
            }}
            .loading-logo {{
                margin-bottom: 32px;
                animation: pulse 2s ease-in-out infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ transform: scale(1); opacity: 1; }}
                50% {{ transform: scale(1.05); opacity: 0.9; }}
            }}
            .loading-title {{
                font-size: 52px;
                font-weight: 900;
                margin-bottom: 12px;
                letter-spacing: 1px;
                font-family: 'Merriweather', Georgia, serif;
            }}
            .loading-title-health {{
                color: #5eead4;
            }}
            .loading-title-net {{
                color: #5eead4;
            }}
            .loading-subtitle {{
                font-size: 16px;
                color: #94a3b8;
                margin-bottom: 56px;
                font-weight: 400;
                letter-spacing: 1px;
                text-transform: uppercase;
                font-family: 'Lato', sans-serif;
            }}
            .loading-bar-container {{
                width: 300px;
                height: 4px;
                background: rgba(15, 23, 42, 0.9);
                border-radius: 2px;
                overflow: hidden;
                border: 1px solid rgba(94, 234, 212, 0.4);
            }}
            .loading-bar {{
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, #0d9488, #5eead4);
                animation: loading 1.5s ease-in-out infinite;
            }}
            @keyframes loading {{
                0% {{ transform: translateX(-100%); }}
                100% {{ transform: translateX(100%); }}
            }}
            .loading-text {{
                margin-top: 24px;
                font-size: 14px;
                color: #64748b;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-family: 'Lato', sans-serif;
            }}
            </style>
            <div class="loading-container">
                <div class="loading-logo">{logo_html}</div>
                <div class="loading-title">
                    <span class="loading-title-health">Health</span><span class="loading-title-net">Net</span>
                </div>
                <div class="loading-subtitle">Sistema de Rutas de Emergencia</div>
                <div class="loading-bar-container">
                    <div class="loading-bar"></div>
                </div>
                <div class="loading-text">Inicializando Sistema</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        import time

        time.sleep(1.5)
        G, nodos_df = load_data_cached()

        df_temp = nodos_df.copy()
        df_temp["es_parada"] = False
        ruta_base = generar_mapa_con_ruta(
            G, df_temp, ruta=None, nombre_html="mapa_base.html", ruta_ordenada=None
        )

        st.session_state["data_loaded"] = True
        st.session_state["G"] = G
        st.session_state["nodos_df"] = nodos_df
        st.session_state["map_html"] = ruta_base

        time.sleep(0.5)
        st.rerun()

    G = st.session_state["G"]
    nodos_df = st.session_state["nodos_df"]

    logo_b64_navbar = get_logo_base64()
    logo_html_navbar = (
        f'<img src="data:image/png;base64,{logo_b64_navbar}" class="navbar-logo">'
        if logo_b64_navbar
        else '<div style="width: 40px; height: 40px; background: #0d9488; border-radius: 50%;"></div>'
    )

    nodos_count = G.number_of_nodes()
    aristas_count = G.number_of_edges()

    st.markdown(
        f"""
        <div class="navbar">
            <div class="navbar-logo-section">
                {logo_html_navbar}
                <span class="navbar-separator">|</span>
                <div class="navbar-text-block">
                    <div class="navbar-title">HealthNet</div>
                    <div class="navbar-subtitle">Sistema de Rutas de Emergencia</div>
                </div>
            </div>
            <div class="navbar-right">
                <span class="navbar-metric-label">NODOS</span>
                <span class="navbar-metric-value">{nodos_count}</span>
                <span class="navbar-separator">|</span>
                <span class="navbar-metric-label">ARISTAS</span>
                <span class="navbar-metric-value">{aristas_count}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mapa_id = dict(zip(nodos_df["nombre"], nodos_df["node_id"]))
    logo_b64 = get_logo_base64()

    with st.sidebar:
        logo_sidebar = (
            f'<img src="data:image/png;base64,{logo_b64}" style="width:60px; height:60px; object-fit:contain; margin:0 auto; display:block; filter: drop-shadow(0 4px 12px rgba(13, 148, 136, 0.5));">'
            if logo_b64
            else ""
        )

        st.markdown(
            f"""
            <div style="text-align: center; padding: 24px 0; margin-bottom: 24px;
                        background: linear-gradient(135deg, rgba(13, 148, 136, 0.18) 0%, rgba(15, 118, 110, 0.08) 100%);
                        border-radius: 8px; border: 1px solid rgba(94, 234, 212, 0.4);">
                {logo_sidebar}
                <h2 style="margin: 16px 0 0 0; font-size: 18px; font-weight: 700; letter-spacing: 1px;">
                    Panel de Control
                </h2>
                <p style="color: #ccfbf1; font-size: 11px; margin: 8px 0 0 0; font-weight: 400; letter-spacing: 0.5px; text-transform: uppercase;">
                    Configuración de Ruta
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --- AMBULANCIA DE ORIGEN ---
        st.markdown(
            """
            <div style="margin-bottom: 4px;">
                <h3 style="margin: 0; font-size: 14px; font-weight: 700; letter-spacing: 0.5px;">
                    Ambulancia de Origen
                </h3>
            </div>
            <div style="height: 1px; background: rgba(94, 234, 212, 0.35); margin-bottom: 20px;"></div>
            """,
            unsafe_allow_html=True,
        )

        ambulancias_df = nodos_df[nodos_df["tipo"] == "ambulancia"]
        ambulancias = sorted(ambulancias_df["nombre"].tolist())

        origen = st.selectbox(
            "Seleccionar ambulancia",
            options=["(Seleccionar)"] + ambulancias,
            index=0,
            label_visibility="collapsed",
            key="selectbox_origen",
        )

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        # --- PUNTOS DE DESTINO ---
        st.markdown(
            """
            <div style="margin-bottom: 4px;">
                <h3 style="margin: 0; font-size: 14px; font-weight: 700; letter-spacing: 0.5px;">
                    Puntos de Destino
                </h3>
            </div>
            <div style="height: 1px; background: rgba(94, 234, 212, 0.35); margin-bottom: 20px;"></div>
            <p style="color: #94a3b8; font-size: 11px; margin: 0 0 10px 0;">
                Seleccione uno o más destinos para calcular la ruta óptima
            </p>
            """,
            unsafe_allow_html=True,
        )

        destinos_df = nodos_df[nodos_df["tipo"].isin(["paciente", "hospital", "clinic"])]
        destinos_lista = sorted(destinos_df["nombre"].tolist())

        destinos_sel = st.multiselect(
            "Destinos disponibles",
            options=destinos_lista,
            label_visibility="collapsed",
            key="multiselect_destinos",
        )

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        # --- OPCIONES DE CÁLCULO ---
        st.markdown(
            """
            <div style="margin-bottom: 4px;">
                <h3 style="margin: 0; font-size: 14px; font-weight: 700; letter-spacing: 0.5px;">
                    Opciones de Cálculo
                </h3>
            </div>
            <div style="height: 1px; background: rgba(94, 234, 212, 0.35); margin-bottom: 20px;"></div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            btn_simple = st.button("Ruta Simple", use_container_width=True, key="btn_simple")
        with col2:
            btn_multiple = st.button("Ruta Múltiple", use_container_width=True, key="btn_multiple")

        btn_reset = st.button("Resetear Sistema", use_container_width=True, key="btn_reset")

        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        state = st.session_state["map_state"]
        if state["tipo_ruta"] != "base" and state["tiempo"]:
            minutos = int(state["tiempo"] / 60)
            segundos = int(state["tiempo"] % 60)
            st.markdown(
                f"""
                <div class="glass-card" style="animation: slideIn 0.3s ease;">
                    <div style="margin-bottom: 12px;">
                        <p style="color: #10b981; margin: 0; font-weight: 700; font-size: 12px; 
                                  text-transform: uppercase; letter-spacing: 1px;">
                            Estado: Ruta Calculada
                        </p>
                    </div>
                    <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(15, 118, 110, 0.10) 100%);
                                border-radius: 6px; padding: 12px;
                                border-left: 3px solid #10b981;">
                        <div style="margin-bottom: 8px;">
                            <span style="color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                Tiempo Estimado
                            </span>
                            <p style="color: #10b981; margin: 4px 0 0 0; font-size: 18px; font-weight: 700;">
                                {minutos}m {segundos}s
                            </p>
                        </div>
                        <div>
                            <span style="color: #94a3b8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                Tipo de Ruta
                            </span>
                            <p style="color: #e2e8f0; margin: 4px 0 0 0; font-size: 14px; font-weight: 600; text-transform: uppercase;">
                                {state["tipo_ruta"]}
                            </p>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if btn_simple:
            if origen == "(Seleccionar)" or len(destinos_sel) == 0:
                st.error("Seleccione una ambulancia y al menos 1 destino")
            else:
                if len(destinos_sel) > 1:
                    st.session_state["show_warning"] = True
                    st.session_state[
                        "warning_message"
                    ] = f"Se seleccionaron {len(destinos_sel)} destinos. La ruta simple solo utilizó el primer destino: {destinos_sel[0]}. Para múltiples destinos use Ruta Múltiple."
                else:
                    st.session_state["show_warning"] = False

                destino = destinos_sel[0]
                src = mapa_id[origen]
                dst = mapa_id[destino]
                ruta, tiempo = calcular_ruta_optima(G, src, dst)
                orden = [src, dst]
                if ruta and tiempo is not None:
                    st.session_state["map_state"] = {
                        "tipo_ruta": "simple",
                        "ruta": ruta,
                        "tiempo": tiempo,
                        "orden": orden,
                        "nombres_paradas": [origen, destino],
                    }

                    df_mapa = nodos_df.copy()
                    df_mapa["es_parada"] = False
                    df_mapa.loc[
                        df_mapa["nombre"].isin([origen, destino]), "es_parada"
                    ] = True

                    ruta_html = generar_mapa_con_ruta(
                        G,
                        df_mapa,
                        ruta,
                        nombre_html="ruta_simple_emergencia.html",
                        ruta_ordenada=orden,
                    )
                    st.session_state["map_html"] = ruta_html

                    st.success("Ruta simple calculada exitosamente")
                    st.rerun()
                else:
                    st.error("No se encontró una ruta válida")

        if btn_multiple:
            st.session_state["show_warning"] = False

            if origen == "(Seleccionar)" or len(destinos_sel) < 2:
                st.error("Se requiere 1 ambulancia y mínimo 2 destinos")
            else:
                nodo_origen = mapa_id[origen]
                nodos_destinos_raw = [mapa_id[d] for d in destinos_sel]
                nodos_destinos = []
                vistos = set()
                for nid in nodos_destinos_raw:
                    if nid not in vistos:
                        nodos_destinos.append(nid)
                        vistos.add(nid)

                ruta, tiempo, orden = calcular_ruta_tsp(G, nodo_origen, nodos_destinos)

                if ruta and tiempo is not None and orden:
                    st.session_state["map_state"] = {
                        "tipo_ruta": "multiple",
                        "ruta": ruta,
                        "tiempo": tiempo,
                        "orden": orden,
                        "nombres_paradas": [origen] + destinos_sel,
                    }

                    df_mapa = nodos_df.copy()
                    df_mapa["es_parada"] = False
                    df_mapa.loc[
                        df_mapa["nombre"].isin([origen] + destinos_sel),
                        "es_parada",
                    ] = True

                    ruta_html = generar_mapa_con_ruta(
                        G,
                        df_mapa,
                        ruta,
                        nombre_html="ruta_multiple_emergencia.html",
                        ruta_ordenada=orden,
                    )
                    st.session_state["map_html"] = ruta_html

                    st.success("Ruta optimizada calculada (Ruta Múltiple - TSP)")
                    st.rerun()
                else:
                    st.error("Error al calcular ruta múltiple")

        if btn_reset:
            st.session_state["show_warning"] = False
            st.session_state["map_state"] = {
                "tipo_ruta": "base",
                "ruta": None,
                "tiempo": None,
                "orden": None,
                "nombres_paradas": None,
            }

            df_temp = nodos_df.copy()
            df_temp["es_parada"] = False
            ruta_base = generar_mapa_con_ruta(
                G,
                df_temp,
                ruta=None,
                nombre_html="mapa_base.html",
                ruta_ordenada=None,
            )
            st.session_state["map_html"] = ruta_base

            st.info("Sistema reiniciado correctamente")
            st.rerun()

    state = st.session_state["map_state"]
    ruta_html = st.session_state.get("map_html")

    if st.session_state.get("show_warning", False) and state["tipo_ruta"] == "simple":
        minutos = int(state["tiempo"] / 60)
        segundos = int(state["tiempo"] % 60)

        col_warn, col_info = st.columns(2)

        with col_warn:
            st.markdown(
                f"""
                <div class="glass-card" style="background: linear-gradient(135deg, rgba(251, 146, 60, 0.12) 0%, rgba(15, 23, 42, 0.85) 100%);
                            border: 1px solid rgba(251, 146, 60, 0.55); height: 100%;">
                    <div style="display: flex; align-items: flex-start; gap: 16px;">
                        <div style="width: 4px; min-height: 80px; background: linear-gradient(180deg, #fb923c, #f97316); border-radius: 2px;"></div>
                        <div>
                            <p style="color: #fb923c; margin: 0; font-weight: 700; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">
                                Aviso: Múltiples Destinos
                            </p>
                            <p style="color: #94a3b8; margin: 8px 0 0 0; font-size: 12px; line-height: 1.6;">
                                {st.session_state["warning_message"]}
                            </p>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_info:
            st.markdown(
                f"""
                <div class="glass-card" style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(15, 23, 42, 0.9) 100%);
                            border: 1px solid rgba(16, 185, 129, 0.45); height: 100%;">
                    <div style="display: flex; align-items: flex-start; gap: 16px;">
                        <div style="width: 4px; min-height: 80px; background: linear-gradient(180deg, #10b981, #059669); border-radius: 2px;"></div>
                        <div style="flex: 1;">
                            <p style="color: #10b981; margin: 0; font-weight: 700; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">
                                Ruta Simple Calculada
                            </p>
                            <div style="display: flex; gap: 20px; margin-top: 12px;">
                                <div>
                                    <p style="color: #94a3b8; margin: 0; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;">Tiempo</p>
                                    <p style="color: #10b981; margin: 4px 0 0 0; font-weight: 700; font-size: 18px;">{minutos}m {segundos}s</p>
                                </div>
                                <div>
                                    <p style="color: #94a3b8; margin: 0; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;">Destinos</p>
                                    <p style="color: #a78bfa; margin: 4px 0 0 0; font-weight: 700; font-size: 18px;">1</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    elif state["tipo_ruta"] == "base" or not state["ruta"]:
        st.markdown(
            """
            <div class="glass-card" style="margin-bottom: 20px; animation: slideIn 0.3s ease;
                        background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(15, 118, 110, 0.25) 100%);
                        border: 1px solid rgba(94, 234, 212, 0.4);">
                <div style="display: flex; align-items: center; gap: 16px;">
                    <div style="width: 4px; height: 50px; background: linear-gradient(180deg, #0d9488, #0f766e); border-radius: 2px;"></div>
                    <div>
                        <p style="color: #5eead4; margin: 0; font-weight: 700; font-size: 14px; text-transform: uppercase; letter-spacing: 1px;">
                            Vista Base Activa
                        </p>
                        <p style="color: #94a3b8; margin: 6px 0 0 0; font-size: 12px; line-height: 1.6;">
                            Seleccione una ambulancia de origen y uno o más destinos en el panel lateral para calcular la ruta óptima.
                        </p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        minutos = int(state["tiempo"] / 60)
        segundos = int(state["tiempo"] % 60)
        if state["tipo_ruta"] == "simple":
            st.markdown(
                f"""
                <div class="glass-card" style="margin-bottom: 20px; animation: slideIn 0.3s ease;
                            background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(15, 23, 42, 0.9) 100%);
                            border: 1px solid rgba(16, 185, 129, 0.45);">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px;">
                        <div style="display: flex; align-items: center; gap: 16px;">
                            <div style="width: 4px; height: 60px; background: linear-gradient(180deg, #10b981, #059669); border-radius: 2px;"></div>
                            <div>
                                <p style="color: #10b981; margin: 0; font-weight: 700; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                                    Ruta Simple Calculada
                                </p>
                                <p style="color: #94a3b8; margin: 6px 0 0 0; font-size: 12px;">
                                    Trayectoria directa punto a punto | Algoritmo: Dijkstra
                                </p>
                            </div>
                        </div>
                        <div style="display: flex; gap: 24px;">
                            <div style="text-align: center; padding: 12px 20px; background: rgba(16, 185, 129, 0.14);
                                        border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.5);">
                                <p style="color: #94a3b8; margin: 0; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">Tiempo</p>
                                <p style="color: #10b981; margin: 6px 0 0 0; font-weight: 700; font-size: 20px;">
                                    {minutos}m {segundos}s
                                </p>
                            </div>
                            <div style="text-align: center; padding: 12px 20px; background: rgba(167, 139, 250, 0.18);
                                        border-radius: 6px; border: 1px solid rgba(167, 139, 250, 0.5);">
                                <p style="color: #94a3b8; margin: 0; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">Destinos</p>
                                <p style="color: #a78bfa; margin: 6px 0 0 0; font-weight: 700; font-size: 20px;">
                                    1
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            paradas_count = len(state["orden"]) - 1 if state["orden"] else 0
            st.markdown(
                f"""
                <div class="glass-card" style="margin-bottom: 20px; animation: slideIn 0.3s ease;
                            background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(15, 23, 42, 0.9) 100%);
                            border: 1px solid rgba(16, 185, 129, 0.45);">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 20px;">
                        <div style="display: flex; align-items: center; gap: 16px;">
                            <div style="width: 4px; height: 60px; background: linear-gradient(180deg, #10b981, #059669); border-radius: 2px;"></div>
                            <div>
                                <p style="color: #10b981; margin: 0; font-weight: 700; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                                    Ruta Múltiple Optimizada
                                </p>
                                <p style="color: #94a3b8; margin: 6px 0 0 0; font-size: 12px;">
                                    Algoritmo TSP: Vecino más cercano + Optimización 2-opt
                                </p>
                            </div>
                        </div>
                        <div style="display: flex; gap: 24px;">
                            <div style="text-align: center; padding: 12px 20px; background: rgba(16, 185, 129, 0.14);
                                        border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.5);">
                                <p style="color: #94a3b8; margin: 0; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">Tiempo Total</p>
                                <p style="color: #10b981; margin: 6px 0 0 0; font-weight: 700; font-size: 20px;">
                                    {minutos}m {segundos}s
                                </p>
                            </div>
                            <div style="text-align: center; padding: 12px 20px; background: rgba(167, 139, 250, 0.18);
                                        border-radius: 6px; border: 1px solid rgba(167, 139, 250, 0.5);">
                                <p style="color: #94a3b8; margin: 0; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">Paradas</p>
                                <p style="color: #a78bfa; margin: 6px 0 0 0; font-weight: 700; font-size: 20px;">
                                    {paradas_count}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div style="border: 1px solid rgba(94, 234, 212, 0.4); border-radius: 8px; overflow: hidden;
                    box-shadow: 0 8px 32px rgba(15, 23, 42, 0.9); background: rgba(15, 23, 42, 0.85);
                    backdrop-filter: blur(10px);">
        """,
        unsafe_allow_html=True,
    )

    if ruta_html and os.path.exists(ruta_html):
        with open(ruta_html, "r", encoding="utf-8") as f:
            html(f.read(), height=720)

    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()