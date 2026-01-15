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
('addVar', '[{"item":"targetVarName","type":"variable"},{"item":"varValue","type":"value"}]',
'target = task["properties"]["targetVarName"]
value = task["properties"]["varValue"]
print(f"Setting {target} = {value}")
self.conector.variables[target] = value'),

('addResult', '[{"item":"sourceVariable","type":"variable"}]',
$body$
source = task["properties"]["sourceVariable"]
# Busca el valor, si no existe usa el nombre como literal
value = self.conector.variables.get(source, source)
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
import os, uuid, re, json
try:
    __DEBUG = os.getenv("DEBUG", "True") == "True"
except:
    __DEBUG = True

error = False  
try:
    variable = task["properties"].get("variable")
    variableValue = task["properties"].get("variableValue")
    comparator = task["properties"].get("comparator")
    if isinstance(variableValue, str) and variableValue in self.conector.variables:
        variableValue = self.conector.variables[variableValue]
    variableCheckValue = self.conector.variables.get(variable, None)
except Exception as e:
    error = True

if not error:
    election = "false"
    if comparator == "=":
        election = "true" if str(variableCheckValue) == str(variableValue) else "false"
    elif comparator == "<":
        election = "true" if variableCheckValue < variableValue else "false"
    elif comparator == ">":
        election = "true" if variableCheckValue > variableValue else "false"
    elif comparator == "!=":
        election = "true" if str(variableCheckValue) != str(variableValue) else "false"
    else:
        comp_str = comparator.replace("¨", "\"").replace("`", "")
        if comp_str.startswith(("\'", "\"")) and comp_str.endswith(("\'", "\"")):
            comp_str = comp_str[1:-1]
        variable_stack = sorted(self.conector.variables.keys(), key=len, reverse=True)
        temp_map = {v: uuid.uuid4().hex for v in variable_stack}
        for v in variable_stack:
            comp_str = re.sub(r"(?<![\"\'])\b%s\b(?![\"\'])" % re.escape(v), temp_map[v], comp_str)
        for v in variable_stack:
            replacement = f"self.conector.variables[\"{v}\"]"
            comp_str = re.sub(r"\b%s\b" % temp_map[v], replacement, comp_str)
        try:
            if eval(comp_str, {"self": self, "json": json}):
                election = "true"
            else:
                election = "false"
        except:
            election = "false"

    if election in task["branches"]:
        for step in task["branches"][election]:
            if not self.process_step(step):
                break
$body$),

('else', '[]', $body$
import os
if os.getenv("DEBUG") == "True":
    print("[AVAP] Else marker")
$body$),

('end', '[]', $body$
import os
if os.getenv("DEBUG") == "True":
    print("[AVAP] End marker")
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
# Obtener propiedades del nodo
sequence = task.get("sequence", [])
varName = task["properties"].get("varName")
LoopFrom = task["properties"].get("from")
Loopto = task["properties"].get("to")

self.conector.logger.info(f"[AVAP PARSER] ENTERING IN A LOOP SEQUENCE WITH PARAMETERS {varName} {LoopFrom} {Loopto}")

# Inicializar la variable del iterador
try:
    # Si LoopFrom es una variable, obtener su valor, si no, convertir a int
    start_val = int(self.conector.variables.get(LoopFrom, LoopFrom))
except:
    start_val = 0

self.conector.variables[varName] = start_val

# Determinar el límite (watcher)
watcher = None
try:
    if str(Loopto).isnumeric():
        watcher = int(Loopto)
    else:
        watcher = int(self.conector.variables.get(Loopto, Loopto))
except Exception as e:
    self.conector.logger.info(f"ERROR DETERMINING LOOP LIMIT: {e}")
    watcher = 0

# Ejecución del Bucle
while int(self.conector.variables[varName]) <= watcher:
    for stp in sequence:
        if not self.process_step(stp):
            self.conector.logger.info("FAILED PROCESSING STEP INSIDE LOOP")
            break
            
    # Incrementar el iterador
    self.conector.variables[varName] = int(self.conector.variables[varName]) + 1
$body$),

('endLoop', '[]',
$body$
# Marcador de fin de bucle. 
# La lógica recursiva es manejada por el nodo startLoop.
import os
if os.getenv("DEBUG") == "True":
    print("[AVAP] endLoop marker reached")
$body$);


