import random
from locust import HttpUser, task, between

class AVAPMultiScriptUser(HttpUser):
    wait_time = between(0, 0) # Carga máxima

    # Definimos 5 scripts con estructuras lógicas diferentes
    scripts_pool = [
        "addParam(n, 'Rafa')\naddResult(n)",
        "function calc(a){ return a * 1.21 }\nval = calc(100)\naddResult(val)",
        "x = 50 + 50\ny = x / 2\naddResult(y)",
        "msg = 'Status: ' + 'Active'\naddResult(msg)",
        "if(1, 1, '=')\n  addParam(status, 'OK')\nend()\naddResult(status)"
    ]

    @task
    def test_variable_load(self):
        # Seleccionamos un script al azar para "engañar" al servidor continuamente
        selected_script = random.choice(self.scripts_pool)
        
        payload = {
            "script": selected_script,
            "variables": {"nombre": "Tester", "level": random.randint(1, 100)}
        }
        
        self.client.post("/api/v1/execute?name=Benchmark", json=payload)