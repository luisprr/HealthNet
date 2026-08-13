import unittest
from unittest.mock import patch

import networkx as nx
import pandas as pd

import app


def agregar_via(grafo, origen, destino, tiempo):
    grafo.add_edge(
        origen,
        destino,
        travel_time=float(tiempo),
        length=float(tiempo),
        osmid=int(origen) * 1000 + int(destino) + 1,
    )


class RutasTest(unittest.TestCase):
    def test_ruta_simple_usa_tiempo_de_viaje(self):
        grafo = nx.MultiDiGraph()
        agregar_via(grafo, 0, 1, 9)

        ruta, tiempo = app.calcular_ruta_optima(grafo, 0, 1)

        self.assertEqual(ruta, [0, 1])
        self.assertEqual(tiempo, 9)

    def test_tsp_evade_un_sumidero_hasta_la_ultima_parada(self):
        grafo = nx.MultiDiGraph()
        agregar_via(grafo, 0, 1, 1)
        agregar_via(grafo, 0, 2, 2)
        agregar_via(grafo, 2, 1, 1)

        resultado = app.calcular_ruta_tsp(grafo, 0, [1, 2])

        self.assertIsNone(resultado["error"])
        self.assertEqual(resultado["orden_nodos"], [0, 2, 1])
        self.assertEqual(resultado["ruta"], [0, 2, 1])

    def test_tsp_falla_completo_en_vez_de_omitir_destinos(self):
        grafo = nx.MultiDiGraph()
        agregar_via(grafo, 0, 1, 1)
        grafo.add_node(2)

        resultado = app.calcular_ruta_tsp(grafo, 0, [1, 2])

        self.assertIsNotNone(resultado["error"])
        self.assertEqual(resultado["ruta"], [])
        self.assertEqual(resultado["no_visitados"], [1, 2])

    def test_entidades_en_el_mismo_nodo_siguen_siendo_dos_paradas(self):
        grafo = nx.MultiDiGraph()
        agregar_via(grafo, 0, 1, 1)
        agregar_via(grafo, 1, 0, 1)

        resultado = app.calcular_ruta_tsp(grafo, 0, [1, 1])

        self.assertIsNone(resultado["error"])
        self.assertEqual(resultado["orden_indices"], [0, 1, 2])
        self.assertEqual(resultado["orden_nodos"], [0, 1, 1])

    def test_mapa_conserva_entidades_que_comparten_nodo(self):
        grafo = nx.MultiDiGraph(crs="EPSG:4326")
        grafo.add_node(0, x=-77.03, y=-12.12)
        agregar_via(grafo, 0, 0, 1)
        entidades = pd.DataFrame(
            [
                {
                    "entity_id": "ambulancia:1",
                    "lat": -12.12,
                    "lon": -77.03,
                    "tipo": "ambulancia",
                    "nombre": "Ambulancia 1",
                    "node_id": 0,
                },
                {
                    "entity_id": "paciente:1",
                    "lat": -12.12,
                    "lon": -77.03,
                    "tipo": "paciente",
                    "nombre": "Paciente 1",
                    "node_id": 0,
                },
            ]
        )

        mapa = app.generar_mapa(
            grafo,
            entidades,
            ruta=[0],
            paradas=["ambulancia:1", "paciente:1"],
        )

        self.assertIn("Ambulancia 1", mapa)
        self.assertIn("Paciente 1", mapa)

    def test_popup_escapa_html_externo(self):
        ataque = '<img src=x onerror="alert(1)">'

        popup = app._popup(ataque, "clinic").html.render()

        self.assertNotIn(ataque, popup)
        self.assertIn("&lt;img", popup)

        with patch.object(app.st, "markdown") as markdown:
            app.ficha_ruta("1m", [], secuencia=["Origen", ataque])
        tarjeta = markdown.call_args.args[0]
        self.assertNotIn(ataque, tarjeta)
        self.assertIn("&lt;img", tarjeta)

    def test_geojson_solicita_la_misma_metrica_de_la_ruta(self):
        grafo = nx.MultiDiGraph()
        with (
            patch.object(
                app.ox.routing,
                "route_to_gdf",
                side_effect=RuntimeError("fallo de geometria"),
            ) as route_to_gdf,
            self.assertRaisesRegex(RuntimeError, "fallo de geometria"),
        ):
            app.geojson_ruta(grafo, [0, 1])

        route_to_gdf.assert_called_once_with(grafo, [0, 1], weight="travel_time")

    def test_error_de_openstreetmap_no_se_oculta(self):
        with (
            patch.object(
                app.ox,
                "features_from_place",
                side_effect=RuntimeError("Overpass no disponible"),
            ),
            self.assertRaisesRegex(RuntimeError, "Overpass no disponible"),
        ):
            app._descargar_pois("Lugar de prueba")

    def test_reset_limpia_resultado_y_widgets(self):
        estado = {
            "ruta": {"tipo": "simple"},
            "aviso": "mensaje",
            "mapa": "html",
            "origen_id": "ambulancia:1",
            "destinos_ids": ["paciente:1"],
        }
        with patch.object(app.st, "session_state", estado):
            app.resetear()

        self.assertEqual(estado["ruta"]["tipo"], "base")
        self.assertEqual(estado["origen_id"], app.SIN_ASIGNAR)
        self.assertEqual(estado["destinos_ids"], [])
        self.assertIsNone(estado["mapa"])


if __name__ == "__main__":
    unittest.main()
