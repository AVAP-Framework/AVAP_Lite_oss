-- Original Commands
CREATE TABLE IF NOT EXISTS obex_dapl_functions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    interface TEXT,
    description TEXT,
    type VARCHAR(50),
    logic BOOLEAN,
    componenttype VARCHAR(50),
    service VARCHAR(50),
    command VARCHAR(50),
    code TEXT
);

-- Bytecode
CREATE TABLE IF NOT EXISTS avap_bytecode (
    id SERIAL PRIMARY KEY,
    command_name VARCHAR(100) UNIQUE NOT NULL,
    bytecode BYTEA,
    version INTEGER DEFAULT 1,
    compiled_at TIMESTAMP DEFAULT NOW(),
    source_hash VARCHAR(64),
    is_verified BOOLEAN DEFAULT FALSE
);

-- Inserting commands
INSERT INTO obex_dapl_functions (name, interface, code) VALUES
(
    'addVar', 
    '[{"item":"targetVarName","type":"variable"},{"item":"varValue","type":"value"}]',
    $body$
target = task["properties"]["targetVarName"]
raw_value = task["properties"]["varValue"]

# Resolución Inteligente
# 1. ¿Es una variable existente?
if raw_value in self.conector.variables:
    resolved_value = self.conector.variables[raw_value]
# 2. ¿Es un número (string que representa un entero)?
elif isinstance(raw_value, str) and raw_value.isdigit():
    resolved_value = int(raw_value)
# 3. ¿Es ya un número (int/float)?
elif isinstance(raw_value, (int, float)):
    resolved_value = raw_value
# 4. En cualquier otro caso, es un literal
else:
    resolved_value = raw_value

print(f"Setting {target} = {resolved_value}")
self.conector.variables[target] = resolved_value
$body$
),

('addResult', '[{"item":"sourceVariable","type":"variable"}]',
$body$
source = task["properties"]["sourceVariable"]
# Si la variable no existe en el conector, devolvemos None (null en JSON)
value = self.conector.variables.get(source, None)
self.conector.results[source] = value
$body$),

('addParam', '[{"item":"param","type":"value"},{"item":"variable","type":"var"}]',
 'param_name = task["properties"].get("param") or next(iter(task["properties"].values()), None)
variable_name = task["properties"].get("variable") or next(reversed(task["properties"].values()), None)

value = None

if hasattr(self.conector, "req"):
    req = self.conector.req
    try:
        # Tornado way: obtener query param
        value = req.get_query_argument(param_name)
    except tornado.web.MissingArgumentError:
        try:
            # Probar en body JSON
            body_data = json.loads(req.request.body.decode())
            value = body_data.get(param_name)
        except:
            # Probar en body_arguments si existe
            try:
                value = req.body_arguments.get(param_name, [None])[0]
            except:
                pass

if variable_name:
    self.conector.variables[variable_name] = value

self.conector.logger.info(f"[AVAP PARSER] ADDING VARIABLE {variable_name} FROM PARAMETER {param_name} VALUE {value}")'),

('if', '[{"item":"variable","type":"variable"},{"item":"variableValue","type":"variable"},{"item":"comparator","type":"value"}]',
$body$
def try_num(v):
    s = str(v).strip().strip('"').strip("'")
    try:
        return float(s) if "." in s else int(s)
    except:
        return s

v1 = try_num(self.conector.variables.get(task["properties"]["variable"], task["properties"]["variable"]))
v2 = try_num(task["properties"]["variableValue"])
op = str(task["properties"]["comparator"]).strip().strip('"').strip("'")

res = False
if op in ["=", "=="]: res = (str(v1) == str(v2))
elif op == ">": res = (v1 > v2)
elif op == "<": res = (v1 < v2)
elif op == ">=": res = (v1 >= v2)
elif op == "<=": res = (v1 <= v2)
elif op == "!=": res = (str(v1) != str(v2))

branch = "true" if res else "false"
if branch in task["branches"]:
    for step in task["branches"][branch]:
        self.process_step(step)

# IMPORTANTE: Sincronizar de vuelta al finalizar la rama
# Esto asegura que 'final' y otras variables lleguen al Executor principal
self.conector.variables.update(self.conector.variables)
$body$),

('end', '[]', 
'# El comando end() marca el fin de un bloque condicional (if/else) o loop.
# La logica de agrupacion se resuelve en el Parser del servidor.
import os
if os.getenv("DEBUG") == "True":
    print("[AVAP] Finalizando bloque de control (end)")
'),
('else', '[]', 
'# El comando else() en AVAP actua como separador de flujo.
# La logica de ejecucion reside en el comando if() padre, 
# el cual accede a task["branches"]["false"].
import os
if os.getenv("DEBUG") == "True":
    print("[AVAP] Entrando en bloque ELSE (marcador)")
'),

('startLoop', '[{"item":"varName","type":"variable"},{"item":"from","type":"value"},{"item":"to","type":"value"}]',
$body$
sequence = task.get("sequence", [])
varName = task["properties"].get("varName")
LoopFrom = task["properties"].get("from")
Loopto = task["properties"].get("to")

def resolve_robust(v):
    # Buscar en variables o usar el literal
    val = self.conector.variables.get(v, v)
    # Limpiar y convertir
    s = str(val).strip().strip('"').strip("'")
    try:
        return int(float(s)) # Maneja "4", "4.0" y " 4 "
    except:
        return 0

start_val = resolve_robust(LoopFrom)
end_val = resolve_robust(Loopto)

self.conector.variables[varName] = start_val

# Ejecución del bucle
while self.conector.variables[varName] <= end_val:
    for stp in sequence:
        if not self.process_step(stp):
            break
    self.conector.variables[varName] += 1

# Sincronizar contexto al salir
self.conector.variables.update(self.conector.variables)
$body$),

('endLoop', '[]',
$body$
# Marcador de fin de bucle. 
# La lógica recursiva es manejada por el nodo startLoop.
import os
if os.getenv("DEBUG") == "True":
    print("[AVAP] endLoop marker reached")
$body$);


