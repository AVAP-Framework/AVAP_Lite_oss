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
'source = task["properties"]["sourceVariable"]
value = self.conector.variables.get(source, source)
print(f"Adding result {source} = {value}")
self.conector.results[source] = value'),

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

(
'return',
'[{"item":"SourceVariable","type":"var"}]',
$$
target = task.get("context")
source_var = task["properties"].get("SourceVariable")

if source_var in self.conector.function_local_vars:
    value = self.conector.function_local_vars[source_var]
elif source_var in self.conector.variables:
    value = self.conector.variables[source_var]
else:
    value = None

if target:
    self.conector.variables[target] = value

self.conector.logger.info(f"[AVAP PARSER] RETURN {source_var} => {value}")
$$
);
