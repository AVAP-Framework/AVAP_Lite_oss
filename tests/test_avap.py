import pytest
import json
import tornado.web
import asyncpg
import os
import sys

# Añadir src al path para poder importar main
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from main import AVAPExecutor, ExecuteHandler

@pytest.fixture
async def app_and_db():
    # URL para GitHub Actions (localhost) o local
    db_url = os.getenv("DB_URL", "postgresql://postgres:password@localhost:5432/avap_db")
    pool = await asyncpg.create_pool(db_url)
    executor = AVAPExecutor(pool)
    
    app = tornado.web.Application([
        (r"/api/v1/execute", ExecuteHandler, dict(executor=executor)),
    ])
    return app, pool

@pytest.mark.asyncio
async def test_avap_full_flow(http_client, app_and_db):
    app, pool = await app_and_db
    
    payload = {
        "script": "addVar(numero, \"123.45\")\naddResult(numero)",
        "variables": {}
    }
    
    response = await http_client.fetch(
        "/api/v1/execute",
        method="POST",
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"}
    )
    
    assert response.code == 200
    data = json.loads(response.body)
    
    # Validaciones
    assert data["success"] is True
    assert data["variables"]["numero"] == 123.45
    assert data["result"]["numero"] == 123.45
    
    await pool.close()