from locust import HttpUser, task, tag

class AVAPLoadTest(HttpUser):
    @task
    def test_pipeline_completo(self):
        self.client.post("/api/v1/execute?name=Benchmark", json={
            "script": "addParam(name,nombre)\naddResult(nombre)",
            "variables": {}
        })