import pytest
import json
import os
import sys
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application

# Añadir src al path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from main import AVAPExecutor, ExecuteHandler
import asyncpg

class TestAVAPFlow(AsyncHTTPTestCase):
    def get_app(self):
        # Este método es requerido por Tornado para levantar el servidor de pruebas
        # Usamos un pool dummy o None inicialmente porque el loop de Tornado
        # debe estar corriendo para inicializar asyncpg
        return Application([
            (r"/api/v1/execute", ExecuteHandler, dict(executor=self.executor)),
        ])

    def setUp(self):
        # Configuramos la base de datos antes de cada test
        import asyncio
        self.db_url = os.getenv("DB_URL", "postgresql://postgres:password@localhost:5432/avap_db")
        
        # Tornado AsyncHTTPTestCase usa su propio loop, necesitamos sincronizar asyncpg
        self.loop = asyncio.get_event_loop()
        self.pool = self.loop.run_until_complete(asyncpg.create_pool(self.db_url))
        self.executor = AVAPExecutor(self.pool)
        
        super().setUp()

    def tearDown(self):
        self.loop.run_until_complete(self.pool.close())
        super().tearDown()

    @gen_test
    async def test_avap_full_flow(self):
        payload = {
            "script": "addVar(numero, \"123.45\")\naddResult(numero)",
            "variables": {}
        }
        
        response = await self.http_client.fetch(
            self.get_url("/api/v1/execute"),
            method="POST",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        assert response.code == 200
        data = json.loads(response.body)
        
        assert data["success"] is True
        assert data["variables"]["numero"] == 123.45
        assert data["result"]["numero"] == 123.45