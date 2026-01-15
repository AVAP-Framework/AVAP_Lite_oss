#!/usr/bin/env python3
"""
AVAP Language Server Lite OSS
"""

import asyncio
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List

import tornado.web
import tornado.ioloop
from tornado.options import define, options

import asyncpg

define("port", default=8888, help="Server Port")
define("db_url", default="postgresql://postgres:password@postgres/avap_db", 
       help="PostgreSQL URL")

# ========== SIMPLIFIED COMPILER ==========
class AVAPCompiler:
    """Minimal compiler - for Phase 1: bytecode = Python code"""
    
    def compile(self, python_code: str, command_name: str) -> Dict[str, Any]:
        """Compile Python code to 'bytecode' (in Phase 1 it is the same code)"""
        return {
            'bytecode': python_code.encode('utf-8'),
            'source_hash': hashlib.sha256(python_code.encode()).hexdigest()
        }

# ========== AVAP PARSER ==========
class AVAPParser:
    """AVAP Parser -> AVAP Code (as in your current system)"""
    
    def parse(self, script: str) -> List[Dict[str, Any]]:
        """Converts AVAP script to a list of commands"""
        lines = script.strip().split('\n')
        commands = []
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            
            if '(' in line and ')' in line:
                cmd_name = line.split('(')[0].strip()
                args_str = line[line.find('(')+1:line.rfind(')')]
                
                args = self._parse_arguments(args_str)
                
                commands.append({
                    'type': cmd_name,
                    'line_number': line_num,
                    'properties': args
                })
        
        return commands
    
    def _parse_arguments(self, args_str: str) -> List[Any]:
        """Parse arguments while preserving $variables and strings"""
        parts = []
        current = ''
        in_quote = False
        quote_char = None
        
        for char in args_str:
            if char in ['"', "'"] and (not in_quote or quote_char == char):
                in_quote = not in_quote
                quote_char = char if in_quote else None
                current += char
            elif char == ',' and not in_quote:
                parts.append(current.strip())
                current = ''
            else:
                current += char
        
        if current:
            parts.append(current.strip())
        
        return [self._clean_value(p) for p in parts if p]

    def _clean_value(self, value: str) -> Any:
        """Strip quotes from strings and detect basic types"""
        value = value.strip()
        
        # Handle quoted strings
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        
        # Try to convert to numeric if it's not a variable ($var)
        if not value.startswith('$'):
            try:
                if '.' in value:
                    return float(value)
                return int(value)
            except ValueError:
                pass
                
        return value

# ========== SIMPLIFIED EXECUTOR ==========
class AVAPExecutor:
    """AVAP command executor"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.compiler = AVAPCompiler()
        self.parser = AVAPParser()
        self.bytecode_cache: Dict[str, bytes] = {}

    def _evaluate_condition(self, properties: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Evaluates a condition like if(variable, value, comparator)
        comparator: '=', '!=', '<', '>', '<=', '>='
        """
        var_name = properties.get('variable')
        var_value = properties.get('variableValue')
        comparator = properties.get('comparator', '=')

        actual_value = context['variables'].get(var_name, None)

        if comparator == '=':
            return actual_value == var_value
        elif comparator == '!=':
            return actual_value != var_value
        elif comparator == '<':
            return actual_value < var_value
        elif comparator == '>':
            return actual_value > var_value
        elif comparator == '<=':
            return actual_value <= var_value
        elif comparator == '>=':
            return actual_value >= var_value
        else:
            raise ValueError(f"Unknown comparator: {comparator}")

    async def _execute_ast(self, node: Dict[str, Any], context: Dict[str, Any]):
        """
        Executes one AST node, recursively for if/else and loops
        """
        node_type = node.get('type')

        if node_type == 'if':
            condition_met = self._evaluate_condition(node['properties'], context)
            branch = node.get('branches', {}).get('true' if condition_met else 'false', [])
            for child in branch:
                await self._execute_ast(child, context)

        elif node_type == 'loop':
            start = int(node['properties']['from'])
            end = int(node['properties']['to'])
            var_name = node['properties']['varName']

            for i in range(start, end):
                context['variables'][var_name] = i
                for child in node.get('sequence', []):
                    await self._execute_ast(child, context)

        else:
            # Comando simple: addVar, addResult, sha256, etc.
            bytecode = await self._get_bytecode(node_type)
            await self._execute_command(node_type, bytecode, node.get('properties', {}), context)

    
    async def execute_script(self, script: str, variables: Dict[str, Any], req=None) -> Dict[str, Any]:
        """Execute full script"""
        commands = self.parser.parse(script)
        context = {
            'variables': variables.copy(),
            'results': {},
            'logs': [],
            'req': req
        }
        
        for node in commands:
            cmd_start = datetime.now()
            try:
                await self._execute_ast(node, context)
                context['logs'].append({
                    'command': node.get('type'),
                    'duration_ms': (datetime.now() - cmd_start).total_seconds() * 1000,
                    'success': True
                })
            except Exception as e:
                context['logs'].append({
                    'command': node.get('type'),
                    'duration_ms': (datetime.now() - cmd_start).total_seconds() * 1000,
                    'success': False,
                    'error': str(e)
                })
                raise
        return context
    
    async def _get_bytecode(self, command_name: str) -> bytes:
        """Retrieve bytecode from cache or compile it"""
        if command_name in self.bytecode_cache:
            return self.bytecode_cache[command_name]
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT bytecode FROM avap_bytecode WHERE command_name = $1",
                command_name
            )
            if row and row['bytecode']:
                self.bytecode_cache[command_name] = row['bytecode']
                return row['bytecode']
        
            row = await conn.fetchrow(
                "SELECT code FROM obex_dapl_functions WHERE name = $1",
                command_name
            )
            if not row:
                raise ValueError(f"Command not found: {command_name}")
            
            python_code = row['code']
            compilation = self.compiler.compile(python_code, command_name)
            bytecode = compilation['bytecode']
            
            await conn.execute("""
                INSERT INTO avap_bytecode (command_name, bytecode, source_hash)
                VALUES ($1, $2, $3)
                ON CONFLICT (command_name) 
                DO UPDATE SET bytecode = EXCLUDED.bytecode
            """, command_name, bytecode, compilation['source_hash'])
            
            self.bytecode_cache[command_name] = bytecode
            return bytecode
    
    async def _execute_command(self, cmd_name: str, bytecode: bytes, properties: List[Any], context: Dict[str, Any]):
        """Universal mapper to fix KeyError like 'sourceVariable', 'varValue', etc."""
        python_code = bytecode.decode('utf-8')
        
        # 1. Base dictionary with positional keys
        prop_dict = {str(i): v for i, v in enumerate(properties)}
        
        # 2. Universal Alias Mapping
        if len(properties) >= 1:
            first_arg = properties[0]
            aliases = [
                'targetVarName', 'varName', 'name', 
                'sourceVariable', 'variableName', 'key' # Fixes 'sourceVariable'
            ]
            for alias in aliases:
                prop_dict[alias] = first_arg
            
        if len(properties) >= 2:
            second_arg = properties[1]
            aliases = ['value', 'varValue', 'val', 'newValue', 'content']
            for alias in aliases:
                prop_dict[alias] = second_arg

        class FakeConector:
            def __init__(self, ctx):
                self.variables = ctx['variables']
                self.results = ctx['results']
                self.logger = self
                self.req = ctx.get('req')  # <- aquí añadimos req
            def info(self, msg):
                print(f"[INFO] {msg}")

            def get_param(self, name):
                """Recupera parámetros de query o body según el request"""
                req = self.req
                # 1. Buscar en query arguments
                if req and hasattr(req, 'query_arguments'):
                    if name.encode() in req.query_arguments:
                        return req.query_arguments[name.encode()][0].decode()
                # 2. Buscar en body como JSON
                if req and hasattr(req, 'body'):
                    try:
                        body_data = json.loads(req.body)
                        if name in body_data:
                            return body_data[name]
                    except:
                        pass
                # 3. Buscar en body_arguments (form data)
                if req and hasattr(req, 'body_arguments'):
                    if name.encode() in req.body_arguments:
                        return req.body_arguments[name.encode()][0].decode()
                return None
        
        namespace = {
            'task': {'properties': prop_dict},
            'self': type('obj', (object,), {'conector': FakeConector(context)}),
            '__builtins__': {**__builtins__, 'print': print} 
                        if isinstance(__builtins__, dict) 
                        else {**__builtins__.__dict__, 'print': print}
        }
        
        # Ahora addResult(numero) encontrará 'sourceVariable' en prop_dict
        exec(python_code, namespace)

# ========== HTTP HANDLERS ==========
class ExecuteHandler(tornado.web.RequestHandler):
    def initialize(self, executor):
        self.executor = executor
    
    async def post(self):
        try:
            data = json.loads(self.request.body)
            script = data.get("script", "")
            variables = data.get("variables", {})
            
            if not script:
                raise ValueError("Script cannot be empty")
            
            result = await self.executor.execute_script(script, variables, req=self)
            
            self.write({
                "success": True,
                "result": result['results'],
                "variables": result['variables'],
                "logs": result['logs']
            })
        except Exception as e:
            self.set_status(400)
            self.write({"success": False, "error": str(e)})

class HealthHandler(tornado.web.RequestHandler):
    async def get(self):
        self.write({"status": "healthy", "service": "avap-server", "version": "1.0.2"})

class CompileHandler(tornado.web.RequestHandler):
    def initialize(self, executor):
        self.executor = executor
    
    async def post(self):
        data = json.loads(self.request.body)
        command_name = data.get("command_name")
        if not command_name:
            self.set_status(400)
            self.write({"error": "command_name is required"})
            return
        try:
            if command_name in self.executor.bytecode_cache:
                del self.executor.bytecode_cache[command_name]
            bytecode = await self.executor._get_bytecode(command_name)
            self.write({"success": True, "command": command_name, "bytecode_size": len(bytecode)})
        except Exception as e:
            self.set_status(400)
            self.write({"error": str(e)})

# ========== MAIN SERVER ==========
async def main():
    tornado.options.parse_command_line()
    print("Starting AVAP Server...")
    
    db_pool = await asyncpg.create_pool(
        options.db_url,
        min_size=2,
        max_size=10
    )
    
    executor = AVAPExecutor(db_pool)
    
    app = tornado.web.Application([
        (r"/api/v1/execute", ExecuteHandler, dict(executor=executor)),
        (r"/api/v1/compile", CompileHandler, dict(executor=executor)),
        (r"/health", HealthHandler),
        (r"/", tornado.web.RedirectHandler, {"url": "/health"})
    ])
    
    app.listen(options.port)
    print(f" Server ready at http://localhost:{options.port}")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nServer stopped")
    finally:
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())