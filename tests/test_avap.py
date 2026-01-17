import pytest
import json
import os
import sys
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from main import AVAPExecutor, ExecuteHandler, CompileHandler
import asyncpg

class TestAVAPFlow(AsyncHTTPTestCase):
    def get_app(self):
        if not hasattr(self, 'executor_obj'):
            self.executor_obj = AVAPExecutor(None) 

        return Application([
            (r"/api/v1/execute", ExecuteHandler, dict(executor=self)),
            (r"/api/v1/compile", CompileHandler, dict(executor=self.executor_obj)),
        ])

    def setUp(self):
        self.db_url = os.getenv("DB_URL", "postgresql://postgres:password@localhost:5432/avap_db")
        loop = self.get_new_ioloop()
        self.pool = loop.run_sync(lambda: asyncpg.create_pool(self.db_url))
        self.executor_obj.db_pool = self.pool
        super().setUp()

    def tearDown(self):
        if hasattr(self, 'pool'):
            self.get_new_ioloop().run_sync(self.pool.close)
        super().tearDown()

    async def execute_script(self, script, variables, req=None):
        return await self.executor_obj.execute_script(script, variables, req=req)

    @gen_test
    async def test_1_simple_assignment_and_result(self):
        """Prueba básica de addVar con tipos numéricos y addResult"""
        payload = {
            "script": "addVar(numero, 123.45)\naddResult(numero)",
            "variables": {}
        }
        response = await self.http_client.fetch(self.get_url("/api/v1/execute"), method="POST", body=json.dumps(payload), headers={"Content-Type": "application/json"})
        data = json.loads(response.body)
        assert data["variables"]["numero"] == 123.45
        assert data["result"]["numero"] == 123.45

    @gen_test
    async def test_2_conditionals_if_else(self):
        """Prueba de bloques if/else nativos"""
        script = """
        addVar(rol, "admin")
        if(rol, "admin", =)
            addVar(acceso, "concedido")
        else()
            addVar(acceso, "denegado")
        end()
        addResult(acceso)
        """
        payload = {"script": script, "variables": {}}
        response = await self.http_client.fetch(self.get_url("/api/v1/execute"), method="POST", body=json.dumps(payload))
        data = json.loads(response.body)
        assert data["variables"]["acceso"] == "concedido"
        assert data["result"]["acceso"] == "concedido"

    @gen_test
    async def test_3_loops_and_variable_resolution(self):
        """Prueba de startLoop con límites basados en variables y concatenación"""
        script = """
        addVar(limite, 3)
        startLoop(i, 1, limite)
            ticket = "T-" + str(i)
            addVar(ultimo_ticket, ticket)
        endLoop()
        addResult(ultimo_ticket)
        """
        payload = {"script": script, "variables": {}}
        response = await self.http_client.fetch(self.get_url("/api/v1/execute"), method="POST", body=json.dumps(payload))
        data = json.loads(response.body)
        # El último i es 3, por lo que el ticket debe ser T-3
        assert data["variables"]["ultimo_ticket"] == "T-3"

    @gen_test
    async def test_4_params_from_url(self):
        """Prueba de addParam extrayendo datos de la query string"""
        script = "addParam(user, usuario)\naddResult(usuario)"
        # Pasamos el parámetro en la URL como lo hace el cliente real
        url = self.get_url("/api/v1/execute?user=rafa_test")
        payload = {"script": script, "variables": {}}
        response = await self.http_client.fetch(url, method="POST", body=json.dumps(payload))
        data = json.loads(response.body)
        assert data["result"]["usuario"] == "rafa_test"

    @gen_test
    async def test_5_full_integration_complex(self):
        """Prueba del flujo completo: Params -> Loop -> If -> Results"""
        script = """
        addParam(limit, max)
        addVar(status, "procesando")
        if(max, 0, >)
            startLoop(idx, 1, max)
                val = idx * 10
                addVar(tmp, val)
            endLoop()
            addVar(final, "completado")
        else()
            addVar(final, "error")
        end()
        addResult(final)
        addResult(tmp)
        """
        # Simulamos ?limit=4
        url = self.get_url("/api/v1/execute?limit=4")
        payload = {"script": script, "variables": {}}
        response = await self.http_client.fetch(url, method="POST", body=json.dumps(payload))
        data = json.loads(response.body)
        
        assert data["success"] is True
        assert data["result"]["final"] == "completado"
        # 4 iteraciones * 10 = 40
        assert data["variables"]["tmp"] == 40
        assert data["result"]["tmp"] == 40

    @gen_test
    async def test_6_request_get_variants(self):
        """Prueba de RequestGet con asignación directa, addVar y filtros"""
        # Test de RequestGet simple con variable destino
        script1 = "RequestGet('https://jsonplaceholder.typicode.com/todos/1', '', '', 'mi_api_data')\naddResult(mi_api_data)"
        response1 = await self.http_client.fetch(self.get_url("/api/v1/execute"), method="POST", body=json.dumps({"script": script1, "variables": {}}))
        data1 = json.loads(response1.body)
        assert data1["success"] is True
        assert "userId" in data1["result"]["mi_api_data"]

        # Test de RequestGet con variables mixtas (addVar + Asignación Python)
        script2 = """
        url_objetivo = "https://jsonplaceholder.typicode.com/comments"
        addVar(mis_filtros, "{'postId': 1}")
        RequestGet(url_objetivo, mis_filtros, '', 'datos_recibidos')
        addResult(datos_recibidos)
        """
        response2 = await self.http_client.fetch(self.get_url("/api/v1/execute"), method="POST", body=json.dumps({"script": script2, "variables": {}}))
        data2 = json.loads(response2.body)
        assert len(data2["result"]["datos_recibidos"]) > 0

    @gen_test
    async def test_7_custom_http_status(self):
        """Prueba de la variable especial _status para forzar códigos HTTP (404)"""
        # Envolvemos en un try para que el error de RequestGet no devuelva el 400 del Handler
        script = """
        try()
            RequestGet("https://jsonplaceholder.typicode.com/todos/999999", "", "", "res")
        exception()
        _status = 404
        """
        response = await self.http_client.fetch(
            self.get_url("/api/v1/execute"), 
            method="POST", 
            body=json.dumps({"script": script, "variables": {}}), 
            raise_error=False
        )
        assert response.code == 404

    @gen_test
    async def test_8_try_catch_command_not_found(self):
        """Prueba de try() y exception() ante un comando que no existe"""
        script = """
        try()
            comandoInexistente()
        detalle_error = exception(msg)
        addResult(detalle_error)
        addResult(msg)
        """
        payload = {"script": script, "variables": {"msg": "esperando..."}}
        response = await self.http_client.fetch(self.get_url("/api/v1/execute"), method="POST", body=json.dumps(payload))
        data = json.loads(response.body)
        assert data["success"] is True
        assert "not found" in data["result"]["detalle_error"].lower()
        assert data["result"]["msg"] == data["result"]["detalle_error"]

    @gen_test
    async def test_9_try_catch_with_500_status(self):
        """Prueba de flujo completo: Error de Red -> Exception -> _status = 500"""
        # Usamos la sintaxis de comando puro para asegurar que el parser no lo vea como 'assign'
        script = """
        try()
            RequestGet("https://jsonplaceholder.typicode.com/posts/invalid/error500", "{}", "{}", "res")
        motivo = exception("msg")
        if(motivo, "No error detected", "!=")
            _status = 500
            addVar("mensaje_salida", "Error critico detectado")
            addResult("mensaje_salida")
            addResult("motivo")
        end()
        """
        payload = {
            "variables": {"msg": "esperando..."},
            "script": script
        }
        response = await self.http_client.fetch(
            self.get_url("/api/v1/execute"), 
            method="POST", 
            body=json.dumps(payload), 
            raise_error=False
        )
        
        assert response.code == 500
        data = json.loads(response.body)
        assert data["result"]["mensaje_salida"] == "Error critico detectado"
    
    @gen_test
    async def test_10_pipeline_optimization_logic(self):
        """Verifica que el pipeline elimina código muerto y pre-calcula constantes"""
        # Script con un if(True) que debe desaparecer y una operación 10*5
        script = "if(True):\n    a = 10 * 5\naddVar('res', a)\naddResult('res')"
        payload = {"name": "test_optimizacion", "script": script}
        
        response = await self.http_client.fetch(
            self.get_url("/api/v1/compile"), 
            method="POST", 
            body=json.dumps(payload)
        )
        data = json.loads(response.body)
        
        assert data["success"] is True
        # El optimizador debió reducir los caracteres significativamente
        assert data["optimized_chars"] < data["original_chars"]
        
        # Ahora ejecutamos el comando compilado para ver si da 50
        exec_payload = {"script": "test_optimizacion()", "variables": {}}
        exec_resp = await self.http_client.fetch(
            self.get_url("/api/v1/execute"), 
            method="POST", 
            body=json.dumps(exec_payload)
        )
        exec_data = json.loads(exec_resp.body)
        assert exec_data["result"]["res"] == 50

    @gen_test
    async def test_11_bytecode_persistence_and_security(self):
        """Verifica que el bytecode se guarda en la DB y es recuperable"""
        cmd_name = "comando_persistente"
        script = "addVar('status', 'ok')"
        
        # 1. Compilar
        await self.http_client.fetch(
            self.get_url("/api/v1/compile"), 
            method="POST", 
            body=json.dumps({"name": cmd_name, "script": script})
        )

        # 2. Verificar directamente en la base de datos
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT bytecode FROM avap_bytecode WHERE command_name = $1", cmd_name)
            assert row is not None
            assert isinstance(row['bytecode'], bytes)
            
            # El bytecode debe empezar con el marcador de seguridad (si usas uno) o no estar vacío
            assert len(row['bytecode']) > 0

    @gen_test
    async def test_12_execute_handler_inline_optimization(self):
        """Verifica que el ExecuteHandler también optimiza scripts 'al vuelo'"""
        # Script con cálculos que el optimizador debería resolver
        script = "x = 100 + 200\naddVar('total', x)\naddResult('total')"
        payload = {"script": script, "variables": {}}
        
        response = await self.http_client.fetch(
            self.get_url("/api/v1/execute"), 
            method="POST", 
            body=json.dumps(payload)
        )
        data = json.loads(response.body)
        
        # Si el optimizador funcionó en el Handler, en los logs no debería haber 
        # rastro de la suma, solo del resultado 300
        assert data["variables"]["total"] == 300
        # Comprobar que el primer log es el assign ya optimizado
        assert data["logs"][0]["command"] == "assign"