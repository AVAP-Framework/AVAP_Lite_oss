import pytest
import json
import os
import sys
import asyncio
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.web import Application

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from main import AVAPExecutor, ExecuteHandler
import asyncpg

class TestAVAPFlow(AsyncHTTPTestCase):
    def get_app(self):
        # We initialize executor as None and set it in setUp
        self.executor = None
        return Application([
            (r"/api/v1/execute", ExecuteHandler, dict(executor=self)),
        ])

    def setUp(self):
        super().setUp()
        # Initialize pool using the test's own loop
        self.db_url = os.getenv("DB_URL", "postgresql://postgres:password@localhost:5432/avap_db")
        self.pool = self.io_loop.run_sync(lambda: asyncpg.create_pool(self.db_url))
        self.executor_obj = AVAPExecutor(self.pool)

    def tearDown(self):
        self.io_loop.run_sync(self.pool.close)
        super().tearDown()

    # Proxy to act as the executor object inside the handler
    async def execute_script(self, script, variables):
        return await self.executor_obj.execute_script(script, variables)

    @gen_test
    async def test_avap_full_flow(self):
        payload = {
            "script": "addVar(numero, 123.45)\naddResult(numero)",
            "variables": {}
        }
        
        response = await self.http_client.fetch(
            self.get_url("/api/v1/execute"),
            method="POST",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            raise_error=False # To see the actual error body if it fails
        )
        
        assert response.code == 200, f"Failed with {response.code}: {response.body}"
        data = json.loads(response.body)
        
        assert data["success"] is True
        assert data["variables"]["numero"] == 123.45
        assert data["result"]["numero"] == 123.45