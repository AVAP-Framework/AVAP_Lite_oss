import random
from locust import HttpUser, task, between

class AVAPChaosUser(HttpUser):
    wait_time = between(0, 0)

    scripts_pool = [
        "addParam(n, 'Rafa')\naddResult(n)",
        "function calc(a){ return a * 1.21 }\nval = calc(100)\naddResult(val)",
        "x = 50 + 50\ny = x / 2\naddResult(y)",
        "msg = 'Status: ' + 'Active'\naddResult(msg)",
        "if(1, 1, '=')\n  addParam(status, 'OK')\nend()\naddResult(status)"
    ]
    
    # Script "venenoso": Bucle pesado o lógica que consume más recursos
    heavy_script = "x=0\nwhile(x<1000)\nx=x+1\nend()\naddResult(x)"

    @task
    def test_variable_load(self):
        dice = random.random()
        
        # Escenario A: 1% de Errores Críticos (Peticiones que fallan)
        if dice < 0.01:
            with self.client.post("/api/v1/execute?name=Benchmark", json={"script": "ERROR_SYNTAX{"}, catch_response=True) as response:
                if response.status_code >= 200 and response.status_code < 300:
                    response.failure("Chaos: Server should have failed on syntax error")

        # Escenario B: 5% de Carga Pesada (Scripts que tardan más)
        elif dice < 0.06:
            payload = {"script": self.heavy_script, "variables": {"level": 999}}
            self.client.post("/api/v1/execute?name=Benchmark", json=payload, name="Heavy Load")

        # Escenario C: Tráfico Normal
        else:
            selected_script = random.choice(self.scripts_pool)
            payload = {
                "script": selected_script,
                "variables": {"nombre": "Tester", "level": random.randint(1, 100)}
            }
            self.client.post("/api/v1/execute?name=Benchmark", json=payload)