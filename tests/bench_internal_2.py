import sys, os, asyncio, time, statistics, builtins

# --- CONFIGURACIÓN DE RUTAS ---
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from main import AVAPExecutor, BytecodePacker, execution_semaphore

# Clase con slots (lo que acabamos de implementar)
class ScriptBridge:
    __slots__ = ['conector', 'process_step']
    def __init__(self, conector, process_step):
        self.conector = conector
        self.process_step = process_step

async def run_hybrid_benchmark(executor, iterations=10000):
    script_locust = "addParam(name,nombre)\naddResult(nombre)"
    
    # 1. Bytecodes reales
    bc_param = BytecodePacker.pack("self.conector.variables['nombre'] = task['properties']['0']")
    bc_result = BytecodePacker.pack("self.conector.results['nombre'] = self.conector.variables.get('nombre')")
    
    # Simulación del objeto 'conector'
    class MockConn:
        def __init__(self): 
            self.variables = {"name": "User"}
            self.results = {}
    
    mock_conn = MockConn()
    bridge = ScriptBridge(mock_conn, None)

    print(f"🚀 Benchmarking EJECUCIÓN HÍBRIDA (Síncrona para lógica)")
    latencies = []

    for i in range(iterations):
        t_start = time.perf_counter()
        
        # --- SIMULACIÓN DE EJECUCIÓN DIRECTA (Sin hilos) ---
        # Esto es lo que pasaría si el motor detecta que no es 'is_heavy'
        namespace = {'self': bridge, 'task': {'properties': {'0': 'User'}}}
        
        # Ejecutamos los dos comandos del pipeline directamente
        exec(BytecodePacker.unpack(bc_param), namespace)
        exec(BytecodePacker.unpack(bc_result), namespace)
        
        t_end = time.perf_counter()
        latencies.append((t_end - t_start) * 1000)

    avg = statistics.mean(latencies)
    print("\n" + "="*45)
    print("📊 RESULTADO: VÍA RÁPIDA (HÍBRIDA)")
    print("="*45)
    print(f"Latencia Promedio: {avg:.4f} ms")
    print(f"CAPACIDAD TEÓRICA: {1000/avg:,.0f} RPS")
    print("="*45)

async def main():
    executor = AVAPExecutor(None)
    await run_hybrid_benchmark(executor)

if __name__ == "__main__":
    asyncio.run(main())