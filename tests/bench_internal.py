import sys, os, asyncio, time, statistics, builtins

# --- CONFIGURACIÓN DE RUTAS ---
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from main import AVAPExecutor, BytecodePacker, execution_semaphore

# --- EL OBJETO QUE BUSCA EL MOTOR ---
class MockObj:
    def __init__(self):
        self.variables = {"name": "BenchmarkUser", "nombre": "BenchmarkUser"}
        self.results = {}

async def run_pipeline_benchmark(executor, iterations=5000):
    script_locust = "addParam(name,nombre)\naddResult(nombre)"
    variables_locust = {"name": "BenchmarkUser"}

    # 1. Bytecode compatible con lo que busca tu motor
    executor.bytecode_cache["addParam"] = BytecodePacker.pack("obj.variables[task['properties']['1']] = task['properties']['0']")
    executor.bytecode_cache["addResult"] = BytecodePacker.pack("obj.results[task['properties']['0']] = obj.variables.get(task['properties']['0'])")
    executor.interface_cache["addParam"] = [{"item": "v"}, {"item": "k"}]
    executor.interface_cache["addResult"] = [{"item": "k"}]

    # 2. INYECCIÓN GLOBAL (Para que los hilos lo vean)
    mock_inst = MockObj()
    builtins.obj = mock_inst # Lo metemos en builtins para que sea universal
    executor.obj = mock_inst 

    print(f"🚀 Benchmarking PIPELINE REAL (Simulando Locust)")
    latencies = []

    for i in range(iterations):
        if execution_semaphore.locked(): 
            execution_semaphore.release()
        
        t_start = time.perf_counter()
        try:
            # Flujo completo: Parser -> AST -> Hilos -> Exec
            await executor.execute_script(script_locust, variables_locust)
        except Exception as e:
            print(f"❌ Fallo técnico: {e}")
            break
        
        t_end = time.perf_counter()
        latencies.append((t_end - t_start) * 1000)

    if not latencies: return

    avg = statistics.mean(latencies)
    print("\n" + "="*45)
    print("📊 RESULTADO: PIPELINE COMPLETO (SISTEMA REAL)")
    print("="*45)
    print(f"Latencia Promedio: {avg:.4f} ms")
    print(f"CAPACIDAD TEÓRICA: {1000/avg:,.0f} RPS")
    print("="*45)

async def main():
    executor = AVAPExecutor(None)
    await run_pipeline_benchmark(executor)

if __name__ == "__main__":
    asyncio.run(main())