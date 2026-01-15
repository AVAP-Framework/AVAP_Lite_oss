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
    def __init__(self):
        self.functions: Dict[str, Dict[str, Any]] = {}

    def parse(self, script: str) -> List[Dict[str, Any]]:
        lines = script.strip().split('\n')
        commands = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('//'):
                i += 1
                continue

            # ==== 1. DETECCIÓN EXPLÍCITA DE RETURN ====
            if line.startswith('return '):
                value = line[len('return '):].strip()
                commands.append({
                    'type': 'return',
                    'properties': [value], # Guardamos el nombre de la var como primer elemento
                    'context': None
                })
                i += 1
                continue

            # ==== Definición de función ====
            if line.startswith('function '):
                header = line[len('function '):].strip()
                name = header[:header.find('(')].strip()
                params = header[header.find('(')+1:header.find(')')].split(',')
                params = [p.strip() for p in params if p.strip()]

                i += 1
                body_lines = []
                brace_count = 1
                while i < len(lines) and brace_count > 0:
                    l = lines[i]
                    if '{' in l: brace_count += l.count('{')
                    if '}' in l: brace_count -= l.count('}')
                    body_lines.append(l)
                    i += 1
                body = '\n'.join(body_lines[:-1])

                body_ast = self.parse(body)

                # Buscar variable de retorno para la metadata de la función
                return_var = None
                for node in body_ast:
                    if node.get('type') == 'return':
                        # Tomamos el primer elemento de la lista de propiedades
                        return_var = node['properties'][0] if node['properties'] else None

                self.functions[name] = {
                    'params': params,
                    'return': return_var,
                    'ast': body_ast
                }
                continue

            # ==== Asignación o llamada a función/comando ====
            if '=' in line:
                target, expr = line.split('=', 1)
                target = target.strip()
                expr = expr.strip()
                if '(' in expr and ')' in expr:
                    cmd_name = expr[:expr.find('(')].strip()
                    args_str = expr[expr.find('(')+1:expr.rfind(')')]
                    args = self._parse_arguments(args_str)
                    commands.append({
                        'type': cmd_name,
                        'properties': args,
                        'context': target
                    })
                else:
                    commands.append({
                        'type': 'assign',
                        'context': target,
                        'properties': [expr]
                    })
            else:
                if '(' in line and ')' in line:
                    cmd_name = line[:line.find('(')].strip()
                    args_str = line[line.find('(')+1:line.rfind(')')]
                    args = self._parse_arguments(args_str)
                    commands.append({
                        'type': cmd_name,
                        'properties': args,
                        'context': None
                    })
            i += 1

        return commands


    
    def _parse_arguments(self, args_str: str) -> List[Any]:
        parts = []
        current = ''
        paren_level = 0  # <--- Nuevo: Seguimiento de paréntesis
        in_quote = False
        quote_char = None
        
        for char in args_str:
            if char in ['"', "'"] and (not in_quote or quote_char == char):
                in_quote = not in_quote
                quote_char = char if in_quote else None
                current += char
            elif char == '(' and not in_quote:
                paren_level += 1
                current += char
            elif char == ')' and not in_quote:
                paren_level -= 1
                current += char
            elif char == ',' and not in_quote and paren_level == 0:
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
        self.function_local_vars: Dict[str, Any] = {}

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

    async def _resolve_arg(self, p: Any, context: Dict[str, Any]) -> Any:
        if not isinstance(p, str):
            return p
        
        # 1. ¿Es una llamada a función pura? (ej: extra())
        # Solo resolvemos si tiene paréntesis y NO tiene operadores matemáticos
        if '(' in p and ')' in p and not any(op in p for op in ['+', '-', '*', '/', '%']):
            cmd_name = p[:p.find('(')].strip()
            args_str = p[p.find('(')+1:p.rfind(')')]
            args = self.parser._parse_arguments(args_str)
            sub_node = {'type': cmd_name, 'properties': args, 'context': None}
            return await self._execute_ast(sub_node, context)

        # 2. ¿Es una expresión compleja (Matemáticas o Concatenación)?
        # Si contiene operadores o comillas, forzamos la evaluación de Python
        if any(op in p for op in ['+', '-', '*', '/', '%']) or '"' in p or "'" in p:
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            try:
                return eval(p, {"__builtins__": {}}, full_scope)
            except:
                pass

        # 3. SI ES UNA VARIABLE SIMPLE (ej: res_math)
        # IMPORTANTE: Devolvemos el string tal cual (p) para que el comando 
        # addResult(res_math) reciba el nombre de la variable y no su contenido.
        return p
    

    async def _execute_ast(self, node: Dict[str, Any], context: Dict[str, Any]):
        node_type = node.get('type')
        properties = node.get('properties', [])
        target = node.get("context")

        # 1. GESTIÓN INTERNA DEL RETURN (Keyword, no comando de DB)
        if node_type == 'return':
            # Buscamos el valor en el scope local o global
            var_name = properties[0] if properties else None
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            
            try:
                # Evaluamos por si es una expresión (ej: return a + b)
                value = eval(str(var_name), {}, full_scope)
            except:
                # Si falla, es un literal o el nombre de una variable
                value = full_scope.get(var_name, var_name)
            
            # Devolvemos un paquete especial que detiene la ejecución de la función
            return {"__return__": value}

        # 2. LLAMADA A FUNCIÓN DEFINIDA (ej: mens = saludo("Rafa"))
        if node_type in self.parser.functions:
            func = self.parser.functions[node_type]
            new_locals = {}
            
            current_scope = {**context['variables'], **(self.function_local_vars or {})}

            # Pasar argumentos a la función
            for i, param_name in enumerate(func['params']):
                if i < len(properties):
                    val = await self._resolve_arg(properties[i], context)
                    # Si el resolver devolvió un nombre de variable, obtenemos su valor real ahora
                    if isinstance(val, str) and val in current_scope:
                        val = current_scope[val]
                    new_locals[param_name] = val

            # Stack de ejecución
            prev_locals = self.function_local_vars
            self.function_local_vars = new_locals
            func_value = None

            # Ejecutar líneas de la función
            for child in func['ast']:
                res = await self._execute_ast(child, context)
                # Si un hijo devolvió el paquete __return__, capturamos el valor y rompemos
                if isinstance(res, dict) and "__return__" in res:
                    func_value = res["__return__"]
                    break
            
            self.function_local_vars = prev_locals
            
            # ¡AQUÍ ESTÁ LA MAGIA! 
            # El valor que salió del 'return' se asigna a la variable externa (target)
            if target:
                context['variables'][target] = func_value
            
            return func_value

        # 3. ASIGNACIONES (ej: final_message = ...)
        elif node_type == 'assign':
            expr = properties[0]
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            try:
                value = eval(expr, {}, full_scope)
            except:
                value = full_scope.get(expr, expr)

            context['variables'][target] = value
            if self.function_local_vars is not None:
                self.function_local_vars[target] = value
            return value

        # 4. COMANDOS DE BASE DE DATOS (addVar, addResult...)
        else:
            # Si el parser mandó un "return" aquí por error, lo redirigimos
            if node_type == "return": 
                return await self._execute_ast({'type': 'return', 'properties': properties}, context)

            bytecode = await self._get_bytecode(node_type)
            
            resolved_props = []
            for p in properties:
                # REGLA DE ORO: 
                # Si es una expresión compleja (tiene operadores) o una función anidada, la resolvemos.
                # Si es una palabra simple (nombre de variable), la pasamos como string para que
                # el comando de la DB (que usa .get()) funcione correctamente.
                if isinstance(p, str) and (any(op in p for op in ['+', '-', '*', '/', '%']) or '(' in p):
                    resolved_props.append(await self._resolve_arg(p, context))
                else:
                    # Pasamos el literal o el nombre de la variable tal cual
                    resolved_props.append(p.strip('"\'') if isinstance(p, str) and (p.startswith('"') or p.startswith("'")) else p)

            context["current_target"] = target
            await self._execute_command(node_type, bytecode, resolved_props, context)
            
            res_val = context['variables'].get(target)
            context["current_target"] = None
            return res_val


    async def execute_script(self, script: str, variables: Dict[str, Any], req=None) -> Dict[str, Any]:
        """Execute full script"""
        commands = self.parser.parse(script)

        print("Functions:", list(self.parser.functions.keys()))
        print("Commands to execute:", [c['type'] for c in commands])

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
                self.function_local_vars = ctx.get('function_local_vars', {})
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
            'task': {'properties': prop_dict, 'context': context.get("current_target")},
            'self': type('obj', (object,), {'conector': FakeConector(context)}),
            'tornado': tornado, # <--- Inyectamos tornado
            'json': json,       # <--- Inyectamos json
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
        self.write({"status": "healthy", "service": "avap-server", "version": "1.0.28"})

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