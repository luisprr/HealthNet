# 🏥 HealthNet – Sistema de Rutas de Emergencia

HealthNet es una aplicación web construida con **Streamlit**, **OSMnx**, **NetworkX** y **Folium** que simula un sistema de respuesta a emergencias médicas en la **Ciudad Autónoma de Buenos Aires, Argentina**.

El sistema genera una red vial de la ciudad, identifica hospitales y clínicas, crea pacientes y ambulancias sobre el grafo y permite calcular:

- **Ruta Simple** (Dijkstra, punto a punto).
- **Ruta Múltiple Optimizada** (TSP heurístico: Vecino más cercano + 2-opt).

Además, incluye una interfaz moderna con tema oscuro, barra superior tipo dashboard y panel lateral de configuración.

---

## 🌐 Características principales

- Descarga y construcción de la red vial de **CABA** usando OSMnx.
- Obtención de **POIs de salud**: `hospital` y `clinic`.
- Generación aleatoria de:
  - **200 pacientes**.
  - **40 ambulancias**.
- Cálculo de rutas:
  - **Ruta Simple**: camino mínimo entre una ambulancia y un destino usando **Dijkstra** (`travel_time`).
  - **Ruta Múltiple**:
    - Orden de visita con heurística de **Vecino más cercano**.
    - Mejora de la ruta con **2-opt**.
    - Cálculo de la ruta completa concatenando los tramos óptimos.
- Visualización en mapa interactivo con **Folium**:
  - Red vial de la ciudad.
  - Hospitales, clínicas, pacientes y ambulancias con íconos y colores diferenciados.
  - Ruta resaltada ("Ruta de Emergencia").
  - Leyenda personalizada.
- UI mejorada:
  - **Navbar fija** con nombre del sistema y métricas de nodos/aristas.
  - **Sidebar** tipo panel de control.
  - Tarjetas con estado de la ruta, tipo de cálculo y tiempo estimado.
  - Pantalla de **loading** inicial con logo.

---

## 🧱 Tecnologías utilizadas

- [Python](https://www.python.org/)
- [Streamlit](https://streamlit.io/)
- [OSMnx](https://osmnx.readthedocs.io/)
- [NetworkX](https://networkx.org/)
- [Folium](https://python-visualization.github.io/folium/)
- [Pandas](https://pandas.pydata.org/)
- [Pillow (PIL)](https://pillow.readthedocs.io/)

---

## 📁 Estructura del proyecto

Ejemplo de estructura mínima:

```bash
HealthNet/
├── app.py
├── requirements.txt
└── HealthNetLogo.png   # opcional, logo usado en la UI
```

- **app.py**: Código principal de la aplicación Streamlit.
- **requirements.txt**: Dependencias del proyecto.
- **HealthNetLogo.png**: Logo que se muestra en la navbar, loading y sidebar (si no existe, la app sigue funcionando).

---

## 📦 Requerimientos

Asegúrate de tener instalado:

- **Python 3.10+** (recomendado)
- **pip**

Además, en Windows puede requerir:

- **Microsoft C++ Build Tools** (para algunas dependencias de OSMnx/NetworkX/Shapely, si no las tienes).

---

## 🔧 Instalación

1. Clona o descarga el repositorio en tu máquina:

```bash
git clone <URL_DEL_REPO>
cd HealthNet
```

2. Crea (opcional pero recomendado) un entorno virtual:

```bash
python -m venv venv
venv\Scripts\activate  # Windows
# o
source venv/bin/activate  # Linux/macOS
```

3. Instala las dependencias:

```bash
pip install -r requirements.txt
```

Si tienes problemas con OSMnx o sus dependencias, revisa la [documentación oficial de OSMnx](https://osmnx.readthedocs.io/) para tu sistema operativo.

---

## ▶️ Ejecución de la aplicación

Dentro de la carpeta del proyecto:

```bash
streamlit run app.py
```

Se abrirá la app en tu navegador por defecto (normalmente en `http://localhost:8501`).

---

## 🗺️ Funcionamiento general

### 1. Carga inicial de datos

Al iniciar, la app:

- Muestra una pantalla de loading con el logo de HealthNet.
- Descarga la red vial de:

```python
PLACE_NAME = "Ciudad Autónoma de Buenos Aires, Argentina"
```

- Aplica un filtro de tipos de vía:

```python
custom_filter='["highway"~"primary|secondary|tertiary|residential|unclassified"]'
```

- Calcula velocidades y tiempos de viaje por arista (`edge_speeds` y `edge_travel_times`).
- Obtiene hospitales y clínicas desde OSM (`POI_TAGS = {"amenity": ["hospital", "clinic"]}`).
- Genera:
  - **200 pacientes** (nodos aleatorios de la red).
  - **40 ambulancias** (nodos aleatorios de la red).

Todo esto se cachea con:

```python
@st.cache_resource
def load_data_cached():
    return cargar_y_procesar_datos(PLACE_NAME)
```

### 2. Interfaz de usuario

La app tiene:

**Navbar superior:**
- Logo y nombre: **HealthNet – Sistema de Rutas de Emergencia**.
- Métricas: cantidad de nodos y aristas del grafo.

**Sidebar (Panel de Control):**
- Logo y título del panel.
- Sección "Ambulancia de Origen":
  - `selectbox` para elegir una ambulancia.
- Sección "Puntos de Destino":
  - `multiselect` para elegir pacientes/hospitales/clinics.
- Sección "Opciones de Cálculo":
  - Botón **Ruta Simple**.
  - Botón **Ruta Múltiple**.
  - Botón **Resetear Sistema**.
- Tarjeta con:
  - Tiempo estimado de la ruta.
  - Tipo de ruta (simple o multiple) cuando se ha calculado.

**Zona principal:**
- Mensaje de estado:
  - "Vista Base Activa" (sin rutas).
  - "Ruta Simple Calculada".
  - "Ruta Múltiple Optimizada".
- Tarjetas con:
  - Tiempo total.
  - Cantidad de destinos/paradas.
- Mapa interactivo incrustado (HTML generado con Folium).

### 3. Cálculo de rutas

#### 🔹 Ruta Simple

**Requisitos:**
- 1 ambulancia seleccionada.
- Al menos 1 destino.
- Si hay más de 1 destino seleccionado, se muestra un aviso y solo se usa el primer destino.

**Algoritmo:**
```python
nx.dijkstra_path(G, src, dst, weight="travel_time")
```

**Resultado:**
- Ruta y tiempo para el par (ambulancia, destino).
- Se genera un HTML con la ruta resaltada: `ruta_simple_emergencia.html`.

#### 🔹 Ruta Múltiple (TSP)

**Requisitos:**
- 1 ambulancia de origen.
- Mínimo 2 destinos.

**Pasos:**
1. Desde el nodo de origen, se aplica **Vecino más cercano** sobre los destinos.
2. Se aplica **2-opt** sobre el orden obtenido para mejorar la ruta.
3. Se calcula la ruta completa concatenando tramos óptimos entre cada par consecutivo: `calcular_ruta_optima` (Dijkstra por tramo).

**Resultado:**
- Ruta completa (lista de node_ids).
- Tiempo total acumulado.
- Orden de visita de las paradas.
- HTML generado: `ruta_multiple_emergencia.html`.

### 4. Visualización en el mapa

El mapa se genera con `folium.Map` y:

**Red vial:**
- Capa principal oscura (para contexto).
- Capa adicional "Red vial" con control de capas.

**Ruta de emergencias:**
- Se dibuja con `ox.routing.route_to_gdf` + `GeoJson`.
- Color rojo, grosor mayor, alta opacidad.

**Capas de entidades:**
- Hospitales.
- Clínicas.
- Pacientes.
- Ambulancias.

**Uso de:**
- `MarkerCluster` para hospitales y clínicas.
- `CircleMarker` para pacientes y ambulancias "normales".
- `Marker` especial para paradas de la ruta (ORIGEN, PARADA 1, PARADA 2, etc.).

**Leyenda** fija en la esquina inferior derecha.

**Controles:**
- Fullscreen.
- LocateControl.
- LayerControl.

---

## 🎨 Estilo y diseño

- **Fuentes:**
  - Títulos: Merriweather.
  - Textos: Lato.
- Tema oscuro con degradados y efecto glassmorphism.
- Navbar fija con métricas en tiempo de ejecución.
- Tarjetas ("glass-card") para estados, tiempos y avisos.
- Popups de mapa customizados con CSS inyectado en el HTML del mapa.

---

## ⚠️ Notas y limitaciones

- Los pacientes y ambulancias se generan de forma aleatoria cada vez que se construye el grafo.
- El cálculo de rutas depende de la calidad de datos de OpenStreetMap para la zona de CABA.
- La optimización TSP es heurística, no garantiza la ruta absolutamente óptima, pero mejora significativamente la ruta inicial.

---

## 📜 Licencia

Este proyecto puede adaptarse a las necesidades académicas y de experimentación con algoritmos de rutas, grafos y visualización geoespacial.
Asegúrate de respetar los términos de uso de OpenStreetMap y las bibliotecas utilizadas.
