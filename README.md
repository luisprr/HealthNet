# HealthNet

HealthNet es un simulador web de rutas de emergencia para Miraflores, Lima. Usa
la red vial de OpenStreetMap, calcula trayectos por tiempo estimado y presenta el
resultado en una interfaz de Streamlit con mapas Folium.

> HealthNet es una demostración académica. Las ambulancias y los pacientes son
> simulados, y los tiempos no incorporan tráfico en vivo ni sustituyen un sistema
> de despacho médico real.

## Funciones

- **Ruta simple:** aplica Dijkstra para conectar una ambulancia con un destino.
- **Ruta múltiple:** usa vecino más cercano y 2-opt para ordenar dos o más
  destinos, manteniendo fijo el origen.
- Valida que todos los destinos puedan visitarse en un único recorrido dirigido;
  si no es posible, rechaza el cálculo completo y explica qué puntos intervienen.
- Mantiene la identidad de hospitales, clínicas, pacientes y ambulancias aunque
  varias entidades estén ancladas al mismo nodo vial.
- Muestra capas, popups, leyenda, itinerario numerado y tiempo estimado.
- Incluye un tema claro y responsivo basado en la paleta teal de HealthNet.

## Requisitos

- Python 3.11 o superior.
- Conexión a internet para la primera carga y para actualizar los datos vencidos.
- Navegador moderno con JavaScript habilitado.

Las versiones verificadas están fijadas en `requirements.txt`.

## Instalación

```bash
python -m venv .venv
```

En Windows:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En macOS o Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run app.py
```

La aplicación queda disponible normalmente en `http://localhost:8501`.

### Uso

1. Selecciona una ambulancia.
2. Selecciona uno o más hospitales, clínicas o pacientes.
3. Usa **Ruta simple** para cubrir el primer destino o **Ruta múltiple** para
   visitar todos los seleccionados.
4. Revisa la secuencia, el tiempo y la traza sobre el mapa.
5. Usa **Resetear sistema** para limpiar ruta, ambulancia y destinos.

## Datos y caché

La primera ejecución descarga la red de conducción y los centros médicos desde
OpenStreetMap. HealthNet conserva durante siete días:

- `.cache/healthnet.graphml`: red vial procesada.
- `.cache/entidades.json`: hospitales, clínicas y entidades simuladas.
- `.cache/metadata.json`: versión, parámetros y fecha de creación.

El metadata incluye el lugar, cantidades simuladas, semilla y configuración de
red. Si cualquiera cambia, el caché se invalida. GraphML y JSON evitan cargar
objetos ejecutables mediante `pickle`. La red se restringe al mayor componente
fuertemente conectado para garantizar rutas entre sus nodos.

Los nombres procedentes de OpenStreetMap se escapan antes de insertarse en HTML.

## Configuración

Los parámetros principales están al inicio de `app.py`:

```python
PLACE_NAME = "Miraflores, Lima, Peru"
N_PACIENTES = 200
N_AMBULANCIAS = 40
SEED = 7
```

La paleta compartida por la interfaz y el mapa se encuentra en el diccionario
`C`. La configuración nativa de Streamlit está en `.streamlit/config.toml` y
debe mantenerse coordinada con esa paleta.

## Algoritmos

### Ruta simple

`networkx.dijkstra_path` minimiza `travel_time`, calculado por OSMnx a partir de
la longitud y velocidad estimada de cada vía.

### Ruta múltiple

1. Calcula una matriz dirigida de tiempos con un Dijkstra por punto.
2. Comprueba que el conjunto completo tenga un orden viable.
3. Construye una solución inicial evitando entrar prematuramente en componentes
   sin salida.
4. Aplica 2-opt sin mover el origen.
5. Verifica cada tramo y solo publica el resultado si visitó todos los destinos.

Es un TSP abierto heurístico: busca una buena ruta, no garantiza el óptimo global.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas cubren rutas directas, grafos dirigidos, destinos imposibles,
entidades colocadas en un mismo nodo, escape HTML, reseteo y caché GraphML/JSON.
GitHub Actions ejecuta estas validaciones en `main`, `develop` y pull requests.

## Estructura

```text
HealthNet/
├── .github/workflows/tests.yml
├── .streamlit/config.toml
├── tests/
├── app.py
├── HealthNetLogo.png
├── README.md
└── requirements.txt
```

## Tecnologías

- Streamlit
- OSMnx y OpenStreetMap
- NetworkX
- Folium
- pandas, NumPy y Shapely
