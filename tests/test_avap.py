import pytest
import json
import os
import sys
import asyncio
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application
import asyncpg
import textwrap

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from main import AVAPExecutor, ExecuteHandler, CompileHandler

class TestAVAPFlow(AsyncHTTPTestCase):
    _pool = None
    _executor = None

    def get_app(self):
        # Aseguramos que el executor existe. No le pasamos el pool aún.
        if not TestAVAPFlow._executor:
            TestAVAPFlow._executor = AVAPExecutor(None)
            
        return Application([
            # IMPORTANTE: Ambos handlers deben apuntar al mismo objeto executor
            (r"/api/v1/execute", ExecuteHandler, dict(executor=TestAVAPFlow._executor)),
            (r"/api/v1/compile", CompileHandler, dict(executor=TestAVAPFlow._executor)),
        ])

    def setUp(self):
        super().setUp()
        self.db_url = os.getenv("DB_URL", "postgresql://postgres:password@localhost:5432/avap_db")
        
        # Inicialización perezosa del pool usando el loop actual de la prueba
        if TestAVAPFlow._pool is None:
            # Usamos el loop de Tornado asignado a esta instancia de test
            TestAVAPFlow._pool = self.io_loop.run_sync(
                lambda: asyncpg.create_pool(self.db_url, min_size=1, max_size=2)
            )
            TestAVAPFlow._executor.db_pool = TestAVAPFlow._pool
        
        # Referencias locales para los tests
        self.pool = TestAVAPFlow._pool
        self.executor_obj = TestAVAPFlow._executor

    @classmethod
    def tearDownClass(cls):
        # Para evitar "Event loop is closed", cerramos el pool de forma aislada
        if cls._pool:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                loop.run_until_complete(cls._pool.close())
            except Exception:
                pass

    def clean_script(self, script):
        """Limpia indentaciones accidentales para evitar el Error 400"""
        return textwrap.dedent(script).strip()

    @gen_test
    async def test_0_simple_assignment_and_result(self):
        script = self.clean_script("""
            x = 10
            y = 20
            resultado = x + y
            addVar('res', resultado)
            addResult('res')
        """)
        payload = {"script": script, "variables": {}}
        
        response = await self.http_client.fetch(
            self.get_url("/api/v1/execute"),
            method="POST",
            body=json.dumps(payload)
        )
        assert response.code == 200
        data = json.loads(response.body)
        assert data["variables"]["res"] == 30

    @gen_test
    async def test_1_simple_assignment_and_result(self):
        """Prueba básica de addVar con tipos numéricos y addResult"""
        # Usamos comillas explícitas para evitar cualquier indentación accidental en la primera línea
        script = "addVar('numero', 123.45)\naddResult('numero')"
        
        payload = {
            "script": script,
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
        
        # Verificamos que los valores coincidan
        assert data["variables"]["numero"] == 123.45
        assert data["result"]["numero"] == 123.45

    @gen_test
    async def test_2_conditionals_if_else(self):
        """Prueba de bloques if/else nativos siguiendo el formato exacto de AVAP"""
        
        # 1. Definimos el script exactamente como en tu curl
        # Nota: Usamos addParam para capturar 'user' de la URL y mapearlo a 'usuario'
        script = (
            "addParam(user, usuario)\n"
            "if(usuario, \"Rafa\", =)\n"
            "  addVar(mensaje, \"Bienvenido Admin\")\n"
            "else()\n"
            "  addVar(mensaje, \"Acceso como Invitado\")\n"
            "end()\n"
            "addResult(mensaje)"
        )
        
        payload = {
            "script": script,
            "variables": {}
        }
        
        # 2. Construimos la URL con el parámetro ?user=Rafa
        url = self.get_url("/api/v1/execute?user=Rafa")
        
        # 3. Realizamos la petición
        response = await self.http_client.fetch(
            url, 
            method="POST", 
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        # 4. Validaciones
        assert response.code == 200
        data = json.loads(response.body)
        
        # Según el script, el resultado debe ser "Bienvenido Admin"
        assert data["variables"]["mensaje"] == "Bienvenido Admin"
        assert data["result"]["mensaje"] == "Bienvenido Admin"