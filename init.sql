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
self.conector.results[source] = value');
