# HealthNet - Sistema de Rutas de Emergencia

Sistema inteligente de optimización de rutas para ambulancias y servicios de emergencia médica, desarrollado con Python y Streamlit.

## Descripción

HealthNet es una aplicación web que permite calcular rutas óptimas para ambulancias en entornos urbanos. Utiliza algoritmos avanzados de grafos para determinar las trayectorias más eficientes entre puntos de origen (ambulancias) y destinos (hospitales, clínicas, pacientes).

El sistema cuenta con dos modos principales:
- **Ruta Simple**: Calcula la trayectoria más rápida entre una ambulancia y un destino específico
- **Ruta Múltiple**: Optimiza el recorrido cuando se necesita visitar varios puntos, minimizando el tiempo total

## Características Principales

- Visualización interactiva de mapas con Folium
- Cálculo de rutas usando el algoritmo de Dijkstra para rutas simples
- Optimización de rutas múltiples mediante TSP (Traveling Salesman Problem) con heurística de vecino más cercano y mejora 2-opt
- Interfaz moderna y responsiva con diseño dark/teal
- Marcadores diferenciados para hospitales, clínicas, pacientes y ambulancias
- Capas de mapa personalizables
- Estimación precisa de tiempos de viaje

## Requisitos del Sistema

- Python 3.8 o superior
- Conexión a internet (para cargar mapas y datos geográficos)
- Navegador web moderno (Chrome, Firefox, Edge, Safari)

## Instalación

### Paso 1: Descargar el proyecto

Descarga los archivos del proyecto en tu computadora. Deberías tener:
- El archivo principal `app.py` (o el nombre que tenga tu código)
- El archivo `HealthNetLogo.png` (logo del sistema)
- Este archivo README.md

### Paso 2: Instalar Python

Si no tienes Python instalado:
1. Ve a [python.org](https://www.python.org/downloads/)
2. Descarga Python 3.8 o superior
3. Durante la instalación, marca la opción "Add Python to PATH"

### Paso 3: Instalar las dependencias

Abre una terminal o símbolo del sistema en la carpeta del proyecto y ejecuta:
```bash
pip install streamlit folium networkx osmnx pandas Pillow
```

Si tienes problemas con la instalación, intenta instalar las bibliotecas una por una:
```bash
pip install streamlit
pip install folium
pip install networkx
pip install osmnx
pip install pandas
pip install Pillow
```

## Uso

### Iniciar la aplicación

1. Abre una terminal en la carpeta del proyecto
2. Ejecuta el siguiente comando:
```bash
streamlit run app.py
```

(Reemplaza `app.py` con el nombre real de tu archivo si es diferente)

3. La aplicación se abrirá automáticamente en tu navegador
4. Si no se abre automáticamente, ve a: `http://localhost:8501`

### Usar la aplicación

1. **Espera la carga inicial**: La primera vez puede tardar unos minutos en cargar todos los datos de la red vial

2. **Seleccionar origen**: En el panel lateral, elige una ambulancia de la lista desplegable

3. **Seleccionar destinos**: Marca uno o más destinos (hospitales, clínicas, pacientes)

4. **Calcular ruta**:
   - Haz clic en "Ruta Simple" si seleccionaste un solo destino
   - Haz clic en "Ruta Múltiple" si seleccionaste varios destinos

5. **Ver resultados**: El mapa mostrará la ruta calculada con el tiempo estimado

6. **Resetear**: Usa el botón "Resetear Sistema" para volver al estado inicial

## Configuración

### Cambiar la ubicación geográfica

Por defecto, el sistema está configurado para el distrito de Miraflores en Lima, Perú. Para cambiar la ubicación:

1. Abre el archivo del código
2. Busca la línea que dice:
```python
   PLACE_NAME = "Miraflores, Lima, Peru"
```
3. Cámbiala por una ciudad completa, por ejemplo:
```python
   PLACE_NAME = "Lima, Perú"
```
   o
```python
   PLACE_NAME = "Ciudad Autónoma de Buenos Aires, Argentina"
```
Colocar áreas más grandes, exigirá más recursos.

### Personalizar colores

Puedes modificar los colores de los marcadores editando el diccionario `COLORES`:
```python
COLORES = {
    "hospital": "#e63946",      # Rojo
    "clinic": "#a06cd5",        # Púrpura
    "paciente": "#457b9d",      # Azul
    "ambulancia": "#2a9d8f",    # Verde azulado
}
```

## Estructura del Proyecto
```
HealthNet/
│
├── app.py                    # Código principal de la aplicación
├── HealthNetLogo.png         # Logo del sistema
├── README.md                 # Este archivo
│
└── (archivos generados automáticamente)
    ├── mapa_base.html
    ├── ruta_simple_emergencia.html
    └── ruta_multiple_emergencia.html
```

## Algoritmos Utilizados

### Ruta Simple - Dijkstra
Encuentra el camino más corto entre dos puntos considerando los tiempos de viaje en cada segmento de la red vial.

### Ruta Múltiple - TSP con 2-opt
1. **Nearest Neighbor**: Construye una ruta inicial visitando siempre el destino más cercano
2. **2-opt**: Mejora iterativamente la ruta intercambiando segmentos hasta que no se puedan hacer más mejoras

## Solución de Problemas

### La aplicación no inicia
- Verifica que todas las dependencias estén instaladas
- Asegúrate de estar en la carpeta correcta del proyecto
- Comprueba que el archivo `HealthNetLogo.png` esté en la misma carpeta

### Error al cargar datos geográficos
- Verifica tu conexión a internet
- Intenta con una ciudad más grande si tu ubicación no tiene suficientes datos

### El mapa no se muestra
- Refresca la página del navegador
- Verifica que no haya bloqueadores de JavaScript activos

### Instalación de osmnx falla
OSMnx puede requerir dependencias adicionales. En Windows:
```bash
pip install wheel
pip install osmnx
```

En Mac/Linux:
```bash
pip install osmnx
```

## Requisitos Técnicos

- **Memoria RAM**: Mínimo 4GB recomendado (8GB para ciudades grandes)
- **Espacio en disco**: Al menos 500MB libres
- **Procesador**: Cualquier procesador moderno de doble núcleo o superior

## Créditos

Desarrollado con:
- Streamlit - Framework de aplicaciones web
- Folium - Visualización de mapas
- OSMnx - Datos de OpenStreetMap
- NetworkX - Algoritmos de grafos

## Notas Adicionales

- La primera carga puede tardar varios minutos dependiendo del tamaño de la ciudad
- Los datos se cachean localmente para mejorar el rendimiento en ejecuciones posteriores
- El sistema genera 200 pacientes y 40 ambulancias de manera aleatoria para demostración

