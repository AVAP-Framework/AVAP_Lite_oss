#!/usr/bin/env python3
"""
AVAP Language Server Lite OSS
"""

import asyncio
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List

import nest_asyncio
nest_asyncio.apply() 

import tornado.web
import tornado.ioloop
from tornado.options import define, options

import asyncpg

define("port", default=8888, help="Server Port")
define("db_url", default="postgresql://postgres:password@postgres/avap_db", 
       help="PostgreSQL URL")


class FakeConector:
    def __init__(self, ctx):
        self.variables = ctx['variables']
        self.function_local_vars = ctx.get('function_local_vars', {})
        self.results = ctx['results']
        self.logger = self
        self.req = ctx.get('req')
    def info(self, msg):
        print(f"[INFO] {msg}")

    def get_param(self, name):
        """Retrieve query or body parameters depending on the request."""
        req = self.req
        # 1. Search in query arguments
        if req and hasattr(req, 'query_arguments'):
            if name.encode() in req.query_arguments:
                return req.query_arguments[name.encode()][0].decode()
        # 2. Search in body as JSON
        if req and hasattr(req, 'body'):
            try:
                body_data = json.loads(req.body)
                if name in body_data:
                    return body_data[name]
            except:
                pass
        # 3. Search in body_arguments (form data)
        if req and hasattr(req, 'body_arguments'):
            if name.encode() in req.body_arguments:
                return req.body_arguments[name.encode()][0].decode()
        return None
            

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
        stack = [commands] 
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('//'):
                i += 1
                continue

            # ==== CONDITIONALS BLOCKS ====
            if line.startswith('if(') or line.startswith('if ('):
                args_str = line[line.find('(')+1:line.rfind(')')]
                args = self._parse_arguments(args_str)
                if_node = {'type': 'if', 'properties': args, 'branches': {'true': [], 'false': []}}
                stack[-1].append(if_node)
                stack.append(if_node['branches']['true'])
                i += 1
                continue
            
            elif line.startswith('else()') or line.startswith('else ('):
                if len(stack) > 1:
                    stack.pop() 
                    if_node = stack[-1][-1]
                    stack.append(if_node['branches']['false'])
                i += 1
                continue

            elif line.startswith('end()') or line.startswith('endLoop()'):
                if len(stack) > 1:
                    stack.pop()
                i += 1
                continue

            # ==== LOOPS BLOCKS ====
            elif line.startswith('startLoop('):
                args_str = line[line.find('(')+1:line.rfind(')')]
                args = self._parse_arguments(args_str)
                loop_node = {'type': 'startLoop', 'properties': args, 'sequence': []}
                stack[-1].append(loop_node)
                stack.append(loop_node['sequence'])
                i += 1
                continue

            # ==== FUNCTIONS DEFINITIONS ====
            if line.startswith('function '):
                header = line[len('function '):].strip()
                name = header[:header.find('(')].strip()
                params = header[header.find('(')+1:header.find(')')].split(',')
                params = [p.strip() for p in params if p.strip()]
                i += 1
                body_lines, brace_count = [], 1
                while i < len(lines) and brace_count > 0:
                    l = lines[i]
                    if '{' in l: brace_count += l.count('{')
                    if '}' in l: brace_count -= l.count('}')
                    body_lines.append(l)
                    i += 1
                body_ast = self.parse('\n'.join(body_lines[:-1]))
                self.functions[name] = {
                    'params': params,
                    'return': next((n['properties'][0] for n in body_ast if n['type'] == 'return'), None),
                    'ast': body_ast
                }
                continue

            # ==== ASSIGNMENTS AND COMMANS (pushed onto the top of the stack) ====
            if line.startswith('return '):
                stack[-1].append({'type': 'return', 'properties': [line[7:].strip()], 'context': None})
            elif '=' in line:
                target, expr = line.split('=', 1)
                target, expr = target.strip(), expr.strip()

                is_pure_command = '(' in expr and expr.endswith(')') and not any(op in expr for op in ['+', '-', '*', '/'])
                
                if is_pure_command:
                    cmd_name = expr[:expr.find('(')].strip()
                    args_str = expr[expr.find('(')+1:expr.rfind(')')]
                    args = self._parse_arguments(args_str)
                    stack[-1].append({'type': cmd_name, 'properties': args, 'context': target})
                else:
                    stack[-1].append({'type': 'assign', 'context': target, 'properties': [expr]})
            else:
                if '(' in line and ')' in line:
                    cmd_name = line[:line.find('(')].strip()
                    args = self._parse_arguments(line[line.find('(')+1:line.rfind(')')])
                    stack[-1].append({'type': cmd_name, 'properties': args, 'context': None})
            i += 1
        return commands


    
    def _parse_arguments(self, args_str: str) -> List[Any]:
        parts = []
        current = ''
        paren_level = 0 
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
        value = value.strip()
        
        # "If it has quotes, it is a string literal; we strip the quotes and return the value.
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        
        # If it is a pure number, cast it (or convert it)
        try:
            if '.' in value: return float(value)
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
        self.interface_cache: Dict[str, List] = {}
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
        
        # 1. s it a pure function call? (e.g., extra())
        # We only resolve it if it has parentheses and NO mathematical operators.
        if '(' in p and ')' in p and not any(op in p for op in ['+', '-', '*', '/', '%']):
            cmd_name = p[:p.find('(')].strip()
            args_str = p[p.find('(')+1:p.rfind(')')]
            args = self.parser._parse_arguments(args_str)
            sub_node = {'type': cmd_name, 'properties': args, 'context': None}
            return await self._execute_ast(sub_node, context)
        
        full_scope = {**context['variables'], **(self.function_local_vars or {})}
        if p in full_scope:
            return full_scope[p]

        # 2. "Is it a complex expression (Mathematics or Concatenation)?
        # "If it contains operators or quotes, we force Python evaluation.
        if any(op in p for op in ['+', '-', '*', '/', '%']) or '"' in p or "'" in p:
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            try:
                safe_builtins = {"str": str, "int": int, "float": float, "len": len}
                return eval(p, {"__builtins__": safe_builtins}, full_scope)
                #return eval(p, {"__builtins__": {}}, full_scope)
            except:
                pass

        # 3. IF A SIMPLE VARIABLE (ej: res_math)
        return p
    

    async def _execute_ast(self, node: Dict[str, Any], context: Dict[str, Any]):
        node_type = node.get('type')
        properties = node.get('properties', [])
        target = node.get("context")

        if node_type == 'if':
            # Delegamos al sistema de comandos de la DB para usar la lógica de smart_cast
            bytecode, interface = await self._get_bytecode('if')
            
            # Preparamos las propiedades para el comando
            resolved_props = []
            for p in properties:
                resolved_props.append(p)

            await self._execute_command('if', bytecode, resolved_props, context, node_full=node, interface=interface)
            
            # Actualizamos contexto
            context['variables'].update(self.conector.variables)
            context['results'].update(self.conector.results)
            return

        if node_type == 'if' and False:
            var_name = properties[0]
            expected = properties[1]
            comp = properties[2] if len(properties) > 2 else "="
            
            actual = context['variables'].get(var_name)
            
            # Evaluación de condición
            condition_met = False
            if comp == "=": condition_met = (str(actual) == str(expected))
            elif comp == "!=": condition_met = (str(actual) != str(expected))
            
            branch = "true" if condition_met else "false"
            for child in node.get('branches', {}).get(branch, []):
                await self._execute_ast(child, context)
            return

        if node_type == 'startLoop':
            var_name = properties[0]
            raw_start = await self._resolve_arg(properties[1], context)
            raw_end = await self._resolve_arg(properties[2], context)
            
            # Ahora raw_end será 5, no "maximo"
            start = int(raw_start)
            end = int(raw_end)
            
            for i in range(start, end + 1):
                context['variables'][var_name] = i
                # IMPORTANT: Synchronize with DB connector
                self.conector.variables[var_name] = i
                
                for child_node in node.get('sequence', []):
                    await self._execute_ast(child_node, context)
            return

        # 1. INTERNAL MANAGEMENT of 'return' KEYWORD (not a DB command)
        if node_type == 'return':
            # Look up the value in the local or global scope
            var_name = properties[0] if properties else None
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            
            try:
                # Evaluate to check if it is an expression (e.g., return a + b)
                value = eval(str(var_name), {}, full_scope)
            except:
                # If it fails, it is either a literal or a variable name
                value = full_scope.get(var_name, var_name)
            
            # Return a special packet that halts function execution
            return {"__return__": value}

        # 2. USER-DEFINED FUNCTION CALL (e.g., mens = greet("Rafa"))
        if node_type in self.parser.functions:
            func = self.parser.functions[node_type]
            new_locals = {}
            
            current_scope = {**context['variables'], **(self.function_local_vars or {})}

            # Pass arguments to the function
            for i, param_name in enumerate(func['params']):
                if i < len(properties):
                    val = await self._resolve_arg(properties[i], context)
                    # If the resolver returned a variable name, we fetch its actual value now
                    if isinstance(val, str) and val in current_scope:
                        val = current_scope[val]
                    try:
                        if isinstance(val, str) and val.isdigit():
                            val = int(val)
                    except:
                        pass
                    new_locals[param_name] = val

            # Execution Stack
            prev_locals = self.function_local_vars
            self.function_local_vars = new_locals
            func_value = None

            # Execute function lines
            for child in func['ast']:
                res = await self._execute_ast(child, context)
                # "If a child returned the __return__ packet, we capture the value and break.
                if isinstance(res, dict) and "__return__" in res:
                    func_value = res["__return__"]
                    break
            
            self.function_local_vars = prev_locals
            
            if target:
                context['variables'][target] = func_value
            
            return func_value

        # 3. ASSIGNMENTS (e.g., final_message = ...)
        elif node_type == 'assign':
            expr = properties[0]
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            safe_builtins = {"str": str, "int": int, "len": len, "float": float}
            internal_func = None
            for f_name in self.parser.functions:
                if expr.startswith(f"{f_name}("):
                    internal_func = f_name
                    break

            if internal_func:
                # Extract the content inside the parentheses
                start_p = expr.find("(") + 1
                end_p = expr.rfind(")")
                raw_args = expr[start_p:end_p]
                
                # Resolve the arguments (e.g., 10 + 5 -> 15)
                resolved_args = eval(raw_args, {"__builtins__": safe_builtins}, full_scope)

                node_call = {
                    'type': internal_func,
                    'properties': [resolved_args],
                    'context': target
                }
                return await self._execute_ast(node_call, context)

            try:
                value = eval(expr, {"__builtins__": safe_builtins}, full_scope)
            except:
                value = full_scope.get(expr, expr)

            context['variables'][target] = value
            if self.function_local_vars is not None:
                self.function_local_vars[target] = value
            return value

        # 4. DATABASE COMMANDS
        else:
            # If the parser sent a 'return' here by mistake, we redirect it.
            if node_type == "return": 
                return await self._execute_ast({'type': 'return', 'properties': properties}, context)

            bytecode, interface = await self._get_bytecode(node_type)
            
            resolved_props = []
            for p in properties:
                # A. Is it a function or calculation? -> Resolve
                if isinstance(p, str) and (('(' in p and ')' in p) or any(op in p for op in ['+', '-', '*', '/', '%'])):
                    resolved_props.append(await self._resolve_arg(p, context))
                
                # B. Is it a quoted literal? -> Strip quotes and pass the text
                elif isinstance(p, str) and ((p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'"))):
                    resolved_props.append(p[1:-1])
                
                # C. "Is it an unquoted word (nombre, name)? -> Pass as is
                # This allows the DB to use it as a KEY to look up variables.
                else:
                    resolved_props.append(p)

            context["current_target"] = target
            await self._execute_command(node_type, bytecode, resolved_props, context, node_full=node, interface=interface)

            context['variables'].update(self.conector.variables)
            context['results'].update(self.conector.results)
            
            res_val = context['variables'].get(target)
            context["current_target"] = None
            return res_val


    async def execute_script(self, script: str, variables: Dict[str, Any], req=None) -> Dict[str, Any]:
        """Execute full script"""
        commands = self.parser.parse(script)

        print("Functions:", list(self.parser.functions.keys()))
        print("Commands to execute:", [c['type'] for c in commands])

        context = {
            'variables': variables, #.copy(),
            'results': {},
            'logs': [],
            'req': req
        }
        
        self.conector = FakeConector(context)

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
    
    async def _get_bytecode(self, command_name: str):
        """"Retrieve the bytecode and the interface (metadata) from the command"""
        # Add an interface cache if it doesn't exist in the __init__
        if not hasattr(self, 'interface_cache'): self.interface_cache = {}

        if command_name in self.bytecode_cache:
            return self.bytecode_cache[command_name], self.interface_cache.get(command_name, [])
        
        async with self.db_pool.acquire() as conn:
            # 1. "Attempt to retrieve pre-compiled bytecode.
            row_bc = await conn.fetchrow(
                "SELECT bytecode FROM avap_bytecode WHERE command_name = $1",
                command_name
            )
            
            # 2. Always obtain the original code and interface to map properties.
            row_func = await conn.fetchrow(
                "SELECT code, interface FROM obex_dapl_functions WHERE name = $1",
                command_name
            )
            
            if not row_func:
                raise ValueError(f"Command not found: {command_name}")

            # "Process interface (the JSON that defines what is a 'param' and what is a 'variable')
            try:
                interface = json.loads(row_func['interface']) if row_func['interface'] else []
            except:
                interface = []
            
            self.interface_cache[command_name] = interface

            if row_bc and row_bc['bytecode']:
                self.bytecode_cache[command_name] = row_bc['bytecode']
                return row_bc['bytecode'], interface
            
            # 3. If there is no bytecode, compile the row_func code.
            python_code = row_func['code']
            compilation = self.compiler.compile(python_code, command_name)
            bytecode = compilation['bytecode']
            
            await conn.execute("""
                INSERT INTO avap_bytecode (command_name, bytecode, source_hash)
                VALUES ($1, $2, $3)
                ON CONFLICT (command_name) 
                DO UPDATE SET bytecode = EXCLUDED.bytecode
            """, command_name, bytecode, compilation['source_hash'])
            
            self.bytecode_cache[command_name] = bytecode
            return bytecode, interface
    
    async def _execute_command(self, cmd_name: str, bytecode: bytes, properties: List[Any], context: Dict[str, Any], node_full: Dict[str, Any] = None, interface: List[Dict] = None):
        python_code = bytecode.decode('utf-8')
        
        # 1. "We create a robust prop_dict with all possible aliases.
        prop_dict = {str(i): v for i, v in enumerate(properties)}
        

        if interface:
            for i, param_def in enumerate(interface):
                if i < len(properties):
                    prop_dict[param_def['item']] = properties[i]

        # 2. We define the bridge function to execute branches (if/loop)
        def process_step_sync(step_node):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._execute_ast(step_node, context))

        builtins_dict = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
        
        namespace = {
            'task': {
                'properties': prop_dict, 
                'context': context.get("current_target"),
                'branches': node_full.get('branches', {}) if node_full else {},
                'sequence': node_full.get('sequence', []) if node_full else []
            },
            'self': type('obj', (object,), {
                'conector': self.conector, #FakeConector(context),
                'process_step': process_step_sync 
            }),
            'tornado': tornado, 
            'json': json,
            're': __import__('re'), 
            'uuid': __import__('uuid'), 
            'os': __import__('os'),
            '__builtins__': {**builtins_dict, 'print': print}
        }
        
        # 4. EXECUTION
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
        self.write({"status": "healthy", "service": "avap-server", "version": "1.0.33"})

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