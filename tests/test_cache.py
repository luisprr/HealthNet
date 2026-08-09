import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pandas as pd

import app


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        raiz = Path(self.temporal.name)
        self.rutas = {
            "CACHE_DIR": raiz,
            "CACHE_GRAPH_FILE": raiz / "healthnet.graphml",
            "CACHE_ENTITIES_FILE": raiz / "entidades.json",
            "CACHE_META_FILE": raiz / "metadata.json",
        }
        self.parches = [
            patch.object(app, nombre, valor) for nombre, valor in self.rutas.items()
        ]
        for parche in self.parches:
            parche.start()

        self.grafo = nx.MultiDiGraph(crs="EPSG:4326")
        self.grafo.add_node(1, x=-77.03, y=-12.12)
        self.grafo.add_node(2, x=-77.02, y=-12.11)
        self.grafo.add_edge(1, 2, osmid=12, length=10.0, travel_time=2.0)
        self.grafo.add_edge(2, 1, osmid=21, length=10.0, travel_time=2.0)
        self.entidades = pd.DataFrame(
            [
                {
                    "entity_id": "ambulancia:1",
                    "lat": -12.12,
                    "lon": -77.03,
                    "tipo": "ambulancia",
                    "nombre": "Ambulancia 1",
                    "node_id": 1,
                },
                {
                    "entity_id": "paciente:1",
                    "lat": -12.11,
                    "lon": -77.02,
                    "tipo": "paciente",
                    "nombre": "Paciente 1",
                    "node_id": 2,
                },
            ]
        )

    def tearDown(self):
        for parche in reversed(self.parches):
            parche.stop()
        self.temporal.cleanup()

    def test_cache_graphml_json_se_puede_recuperar(self):
        app._guardar_cache(self.grafo, self.entidades)

        recuperado = app._cargar_cache()

        self.assertIsNotNone(recuperado)
        grafo, entidades = recuperado
        self.assertTrue(nx.is_strongly_connected(grafo))
        self.assertEqual(set(entidades["entity_id"]), {"ambulancia:1", "paciente:1"})
        graphml = self.rutas["CACHE_GRAPH_FILE"].read_text(encoding="utf-8")
        self.assertTrue(graphml.startswith("<?xml"))

    def test_cache_expirado_no_se_reutiliza(self):
        app._guardar_cache(self.grafo, self.entidades)
        metadata = json.loads(self.rutas["CACHE_META_FILE"].read_text(encoding="utf-8"))
        metadata["created_at"] = 0
        self.rutas["CACHE_META_FILE"].write_text(json.dumps(metadata), encoding="utf-8")

        self.assertIsNone(app._cargar_cache())


if __name__ == "__main__":
    unittest.main()
