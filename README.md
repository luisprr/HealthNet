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
- Interfaz en español e inglés, con selector en la barra superior.
- Arranca sin conexión: los datos geográficos viajan versionados en el
  repositorio.
- Incluye un tema claro y responsivo basado en la paleta teal de HealthNet.

## Requisitos

- Python 3.11 o superior.
- Navegador moderno con JavaScript habilitado.
- No hace falta conexión: los datos van incluidos en `data/`. Solo se
  necesita internet para regenerarlos con `scripts/build_dataset.py`.

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

1. En **Ambulancia de origen**, elige la unidad que sale.
2. En **Destinos**, busca y añade hospitales, clínicas o pacientes. Cada
   destino aparece listado debajo, con el icono de su tipo y un botón para
   quitarlo.
3. En **Cálculo de ruta**, usa **Ruta simple** para cubrir el primer destino
   o **Ruta múltiple** para visitar todos los seleccionados. El botón
   resaltado indica el modo activo.
4. Revisa el tiempo estimado, el número de paradas y la secuencia; la traza
   aparece sobre el mapa con el origen marcado como `A` y las paradas
   numeradas.
5. Usa **Resetear sistema** para limpiar ruta, ambulancia y destinos.

## Datos y caché

HealthNet **no descarga nada al arrancar**. Los datos viajan versionados en
`data/`, de modo que el despliegue funciona en entornos sin salida a Overpass
(Streamlit Community Cloud rechaza esa conexión):

- `data/red_vial.graphml`: red vial procesada.
- `data/entidades.json`: hospitales, clínicas y entidades simuladas.
- `data/manifiesto.json`: firma de configuración y checksums SHA-256.

El orden de carga es `data/` → `.cache/` → descarga de OpenStreetMap. El
snapshot no caduca; el caché local sí, a los siete días.

Para regenerarlo tras cambiar `PLACE_NAME`, las cantidades o la semilla:

```bash
python scripts/build_dataset.py              # descarga de OpenStreetMap
python scripts/build_dataset.py --desde-cache  # reutiliza .cache/ local
```

La firma incluye lugar, cantidades simuladas, semilla y configuración de red: si
alguna cambia, el snapshot deja de considerarse válido. GraphML y JSON evitan
cargar objetos ejecutables mediante `pickle`. La red se restringe al mayor
componente fuertemente conectado para garantizar rutas entre sus nodos.

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

### Idiomas

La interfaz está en español e inglés, con selector en la barra superior. Las
cadenas viven en el diccionario `TEXTOS` y se leen con `t("clave")`; añadir un
idioma es añadir una entrada más. Los nombres de pacientes y ambulancias son
sintéticos y se traducen; los de hospitales y clínicas vienen de OpenStreetMap y
se conservan tal cual.

Streamlit deriva la identidad de un widget de sus parámetros, etiqueta
incluida, así que al traducirla el selector nace vacío. Por eso `cambiar_idioma`
guarda la selección antes del rerun y `_resembrar_seleccion` la repone.

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
├── data/                  # snapshot versionado que usa el despliegue
├── scripts/build_dataset.py
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
