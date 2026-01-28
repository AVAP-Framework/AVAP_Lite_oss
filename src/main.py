#!/usr/bin/env python3
"""
AVAP Language Server Lite OSS
"""
import grpc
import requests
import tornado.web
import uuid
import re
import asyncio
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List
import base64
import time
import gc

gc.set_threshold(7000, 10, 10)

import signal
import queue
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from app.core import avap_pb2

process_executor = ProcessPoolExecutor(max_workers=1)

MAX_WORKERS = 20 
thread_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
execution_semaphore = asyncio.Semaphore(MAX_WORKERS)

import tornado.web
import tornado.ioloop
from tornado.options import define, options

import asyncpg
import struct
import hmac
import hashlib
import ast

import os

# Definition server config

BRAIN_TARGET = '0.0.0.0:50051'
BRAIN_AUTH_TOKEN = 'avap_secret_key_2026'

BRAIN_HOST = os.getenv('BRAIN_HOST', 'avap-definition-engine')
BRAIN_PORT = '50051'


define("port", default=8888, help="Server Port")
define("db_url", default="postgresql://postgres:password@postgres/avap_db", 
       help="PostgreSQL URL")


import ast

class AVAPOptimizer(ast.NodeTransformer):
    """
    Transformador de AST para optimizar el código antes de compilarlo.
    """
    def visit_BinOp(self, node):
        # Constant Folding
        self.generic_visit(node)
        if isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant):
            try:
                # If both sides are numbers, we operate at compile time.
                new_val = eval(compile(ast.Expression(node), "", "eval"))
                return ast.Constant(value=new_val)
            except:
                return node
        return node

    def visit_If(self, node):
        # Dead Code Elimination
        self.generic_visit(node)
        if isinstance(node.test, ast.Constant):
            if node.test.value: # if(True)
                return node.body
            else: # if(False)
                return node.orelse
        return node
    
class BytecodePacker:
    # Header constants
    MAGIC = b'AVAP'  # File identification magic number
    VERSION = 1      # Protocol version
    SECRET_KEY = b'avap_secure_signature_key_2026' # HMAC signing key (use Env Var in prod)

    @classmethod
    def pack(cls, python_code: str) -> bytes:
        """Encapsulates Python code into a signed binary package."""
        payload = python_code.encode('utf-8')
        # Header: Magic(4b) + Version(2b) + PayloadSize(4b) = 10 bytes
        header = struct.pack('>4sHI', cls.MAGIC, cls.VERSION, len(payload))
        
        # Digital Signature: HMAC-SHA256 for integrity and authenticity
        signature = hmac.new(cls.SECRET_KEY, header + payload, hashlib.sha256).digest()
        
        # Structure: [Header][Signature][Payload]
        return header + signature + payload

    @classmethod
    def unpack(cls, data: bytes) -> str:
        """Validates signature and extracts code from binary package."""
        # Minimum size validation (Header 10b + Signature 32b)
        if len(data) < 42:
            raise ValueError("Corrupted bytecode: Insufficient size")

        # Extract and validate Header
        magic, version, p_size = struct.unpack('>4sHI', data[:10])
        if magic != cls.MAGIC:
            raise ValueError("Invalid bytecode: Magic Number mismatch")
        
        # Extract Signature and Payload
        stored_signature = data[10:42]
        payload = data[42:]

        # Validate Digital Signature
        expected_signature = hmac.new(cls.SECRET_KEY, data[:10] + payload, hashlib.sha256).digest()
        if not hmac.compare_digest(stored_signature, expected_signature):
            raise ValueError("SECURITY ALERT! Bytecode has been tampered with or signature is invalid")

        return payload.decode('utf-8')

class FakeConector:
    def __init__(self, ctx):
        self.variables = ctx['variables']
        self.function_local_vars = ctx.get('function_local_vars', {})
        self.results = ctx['results']
        self.logger = self
        self.req = ctx.get('req')
        self.try_level = 0
        self.except_level = []

    def info(self, msg):
        #print(f"[INFO] {msg}")
        pass

    def get_param(self, name):
        """Retrieve query or body parameters depending on the request."""
        req = self.req
        # Search in query arguments
        if req and hasattr(req, 'query_arguments'):
            if name.encode() in req.query_arguments:
                return req.query_arguments[name.encode()][0].decode()
        # Search in body as JSON
        if req and hasattr(req, 'body'):
            try:
                body_data = json.loads(req.body)
                if name in body_data:
                    return body_data[name]
            except:
                pass
        # Search in body_arguments (form data)
        if req and hasattr(req, 'body_arguments'):
            if name.encode() in req.body_arguments:
                return req.body_arguments[name.encode()][0].decode()
        return None
            

# AVAP COMPILER
class AVAPCompiler:
    """Minimal compiler - for Phase 1: bytecode = Python code"""
    
    def compile(self, python_code: str, command_name: str) -> Dict[str, Any]:
        """Compile Python code to 'bytecode' (in Phase 1 it is the same code)"""
        binary_package = BytecodePacker.pack(python_code)
        return {
            'bytecode': binary_package, #python_code.encode('utf-8'),
            'source_hash': hashlib.sha256(python_code.encode()).hexdigest()
        }

# AVAP PARSER
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

            # CONDITIONALS BLOCKS
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

            # LOOPS BLOCKS
            elif line.startswith('startLoop('):
                args_str = line[line.find('(')+1:line.rfind(')')]
                args = self._parse_arguments(args_str)
                loop_node = {'type': 'startLoop', 'properties': args, 'sequence': []}
                stack[-1].append(loop_node)
                stack.append(loop_node['sequence'])
                i += 1
                continue

            # FUNCTIONS DEFINITIONS
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

            # ASSIGNMENTS AND COMMANS
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
        
        # If it has quotes, it is a string literal.
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        
        # If it is a number
        try:
            if '.' in value: return float(value)
            return int(value)
        except ValueError:
            pass
            
        return value
    

class MetricsHandler(tornado.web.RequestHandler):
    def initialize(self, executor):
        self.executor = executor

    async def get(self):
        m = self.executor.metrics
        # OpenMetrics format (Prometheus)
        output = [
            f"# HELP avap_requests_total Total requests received",
            f"# TYPE avap_requests_total counter",
            f"avap_requests_total {m['requests_total']}",
            
            f"# HELP avap_rejects_concurrency Requests rejected due to lack of slots (503)",
            f"# TYPE avap_rejects_concurrency counter",
            f"avap_rejects_concurrency {m['rejects_concurrency']}",

            f"# HELP avap_rejects_timeout Requests terminated by Watchdog (504)",
            f"# TYPE avap_rejects_timeout counter",
            f"avap_rejects_timeout {m['rejects_timeout']}",
            
            f"# HELP avap_active_workers Currently busy execution threads",
            f"# TYPE avap_active_workers gauge",
            f"avap_active_workers {MAX_WORKERS - execution_semaphore._value}"
        ]
        self.set_header("Content-Type", "text/plain; version=0.0.4")
        self.write("\n".join(output))

class ScriptBridge:
    """Static class to inject into the exec namespace."""
    __slots__ = ['conector', 'process_step'] # Memory optimization
    
    def __init__(self, conector, process_step):
        self.conector = conector
        self.process_step = process_step
class AVAPExecutor:
    """AVAP command executor"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.metrics = {
        "requests_total": 0,
        "requests_success": 0,
        "requests_error": 0,
        "rejects_concurrency": 0, 
        "rejects_timeout": 0,  
        "execution_time_ms": 0.0 
        }
        self.compiler = AVAPCompiler()
        self.parser = AVAPParser()
        self.bytecode_cache: Dict[str, bytes] = {}
        self.interface_cache: Dict[str, List] = {}
        self.function_local_vars: Dict[str, Any] = {}
        self.code_object_cache = {}
        self._stub = None
        self.ast_cache = {}
        self.cache_limit = 1000

    def _get_brain_stub(self):
        """Optimized gRPC initialization post-fork"""
        if self._stub is None:
            import grpc
            from app.core import avap_pb2_grpc
            
            # Channel parameters
            options = [
                ('grpc.keepalive_time_ms', 10000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.http2.max_pings_without_data', 0),
                ('grpc.enable_retries', 1),
            ]
            
            channel = grpc.insecure_channel(
                f'{BRAIN_HOST}:{BRAIN_PORT}', 
                options=options
            )
            self._stub = avap_pb2_grpc.DefinitionEngineStub(channel)
            self.metadata = (('x-avap-auth', BRAIN_AUTH_TOKEN),)
        return self._stub

    async def measure_sync_efficiency(self):
        start_sync = time.perf_counter()
        
        await self.sync_full_catalog()
        
        end_sync = time.perf_counter()
        total_time = (end_sync - start_sync) * 1000
        count = len(self.bytecode_cache)
        
        print(f"gRPC Efficiency: {count} commands synchronized in {total_time:.2f} ms")
        print(f"Transfer rate: {total_time/count:.4f} ms per command")

    async def sync_full_catalog(self):
        stub = self._get_brain_stub()
        try:
            # Synchronous call via executor to avoid blocking Tornado
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, lambda: stub.SyncCatalog(avap_pb2.Empty(), metadata=self.metadata)) 
            
            # Temporary structures to ensure an 'all-or-nothing' update.
            new_bytecode = {}
            new_interface = {}
            new_code_objects = {}

            for cmd in response.commands: 
                # Bytecode and source code
                new_bytecode[cmd.name] = cmd.code 
                source = BytecodePacker.unpack(cmd.code) 
                new_code_objects[cmd.name] = compile(source, f"<cmd:{cmd.name}>", "exec")
                
                # Interface (JSON parsing error not added to cache)
                if cmd.interface_json:
                    new_interface[cmd.name] = json.loads(cmd.interface_json) 
                else:
                    new_interface[cmd.name] = []

            # swap
            self.bytecode_cache = new_bytecode
            self.interface_cache = new_interface
            self.code_object_cache = new_code_objects
            
            print(f"[SYNC] Updated and consistent catalog: {len(new_bytecode)} commands.")
            
        except Exception as e:
            print(f"[SYNC] Critical consistency error: {e}")

    def schedule_refresh(self):
        """Schedule next catalog synchronization."""
        async def task():
            await self.sync_full_catalog()
            # Schedule the next execution in 60s.
            tornado.ioloop.IOLoop.current().call_later(60, self.schedule_refresh)
        
        tornado.ioloop.IOLoop.current().add_callback(task)

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
        
        # Functions
        if '(' in p and ')' in p and not any(op in p for op in ['+', '-', '*', '/', '%']):
            cmd_name = p[:p.find('(')].strip()
            args_str = p[p.find('(')+1:p.rfind(')')]
            args = self.parser._parse_arguments(args_str)
            sub_node = {'type': cmd_name, 'properties': args, 'context': None}
            return await self._execute_ast(sub_node, context)
        
        full_scope = {**context['variables'], **(self.function_local_vars or {})}
        if p in full_scope:
            return full_scope[p]

        # Complex expressions.
        if any(op in p for op in ['+', '-', '*', '/', '%']) or '"' in p or "'" in p:
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            try:
                safe_builtins = {"str": str, "int": int, "float": float, "len": len}
                return eval(p, {"__builtins__": safe_builtins}, full_scope)
            except:
                pass

        # A variable
        return p
    

    async def _execute_ast(self, node: Dict[str, Any], context: Dict[str, Any]):
        node_type = node.get('type')
        properties = node.get('properties', [])
        target = node.get("context")

        if node_type == 'if':
            
            bytecode, interface = await self._get_bytecode('if')
            
            # Prepare properties for the command
            resolved_props = []
            for p in properties:
                resolved_props.append(p)

            await self._execute_command('if', bytecode, resolved_props, context, node_full=node, interface=interface)
            
            # update the context
            context['variables'].update(self.conector.variables)
            context['results'].update(self.conector.results)
            return

        if node_type == 'startLoop':
            var_name = properties[0]
            raw_start = await self._resolve_arg(properties[1], context)
            raw_end = await self._resolve_arg(properties[2], context)
            
            start = int(raw_start)
            end = int(raw_end)
            
            for i in range(start, end + 1):
                context['variables'][var_name] = i
                # DB connector synchronization
                self.conector.variables[var_name] = i
                
                for child_node in node.get('sequence', []):
                    await self._execute_ast(child_node, context)
            return

        # 1. INTERNAL MANAGEMENT of return KEYWORD
        if node_type == 'return':
            # Local or global scope
            var_name = properties[0] if properties else None
            full_scope = {**context['variables'], **(self.function_local_vars or {})}
            
            try:
                # Evaluate expression
                value = eval(str(var_name), {}, full_scope)
            except:
                # Is not an expression
                value = full_scope.get(var_name, var_name)
            
            # Return a signal to halts function execution
            return {"__return__": value}

        # Functions call
        if node_type in self.parser.functions:
            func = self.parser.functions[node_type]
            new_locals = {}
            
            current_scope = {**context['variables'], **(self.function_local_vars or {})}

            # Pass arguments to the function
            for i, param_name in enumerate(func['params']):
                if i < len(properties):
                    val = await self._resolve_arg(properties[i], context)
                    # Fetch its actual value now if variable
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

        # 3. ASSIGNMENTS
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
                
                # Resolve the arguments (e.g., 10 + 5 = 15)
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
            # The parser sent a 'return' redirection.
            if node_type == "return": 
                return await self._execute_ast({'type': 'return', 'properties': properties}, context)

            
            bytecode, interface = await self._get_bytecode(node_type)
            
            resolved_props = []
            for p in properties:
                # Resulve a function or calculation
                if isinstance(p, str) and (('(' in p and ')' in p) or any(op in p for op in ['+', '-', '*', '/', '%'])):
                    resolved_props.append(await self._resolve_arg(p, context))
                
                # Strip quotes and pass the text if a quoted literal
                elif isinstance(p, str) and ((p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'"))):
                    resolved_props.append(p[1:-1])
                
                # Unquoted word (nombre, name)
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

        normalized_script = script.strip()
        script_hash = hashlib.md5(normalized_script.encode()).hexdigest()

        if script_hash in self.ast_cache:
            commands = self.ast_cache[script_hash]
        else:
            # Only parse if unknown.
            commands = self.parser.parse(normalized_script)
            
            # Save if space is available.
            if len(self.ast_cache) < self.cache_limit:
                self.ast_cache[script_hash] = commands

        context = {
            'variables': variables, #.copy(),
            'results': {},
            'logs': [],
            'req': req,
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
                error_msg = str(e)
                
                # IF NOT AN ACTIVE TRY (level 0), RAISE ERROR
                if self.conector.try_level <= 0:
                    context['logs'].append({
                        'command': node.get('type'),
                        'duration_ms': (datetime.now() - cmd_start).total_seconds() * 1000,
                        'success': False,
                        'error': error_msg
                    })
                    raise e # this stops execution and returns 400
                
                # ACTIVE TRY (level > 0), CATCH AND CONTINUE
                # Save the error in an special variable to 'exception' be able to read it
                self.conector.variables['__last_error__'] = error_msg
                
                context['logs'].append({
                    'command': node.get('type'),
                    'duration_ms': (datetime.now() - cmd_start).total_seconds() * 1000,
                    'success': False,
                    'error': error_msg
                })
                continue
            
        return context
    
    async def _get_bytecode(self, command_name: str):
        """Retrieve the bytecode and the interface (metadata) from the command"""
        if not hasattr(self, 'interface_cache'): self.interface_cache = {}

        # 1. Check local memory cache (L1 Cache)
        if command_name in self.bytecode_cache:
            bytecode = self.bytecode_cache[command_name]

            return self.bytecode_cache[command_name], self.interface_cache.get(command_name, [])
        
        try:
         
            stub = self._get_brain_stub()
            response = stub.GetCommand(
                avap_pb2.CommandRequest(name=command_name), 
                metadata=self.metadata,
                timeout=2 
)
            interface = json.loads(response.interface_json) if response.interface_json else []
            bytecode = response.code # Already returns the signed binary (BytecodePacker).
            
            self.bytecode_cache[command_name] = bytecode
            self.interface_cache[command_name] = interface
            
            print(f"[DEFINITION] Hit via gRPC: {command_name}")
            return bytecode, interface

        except grpc.RpcError as e:
            # If the error is NOT_FOUND (5), proceed to the local DB.
            # For any other error, log AVAP Definition Server crash.
            if e.code() != grpc.StatusCode.NOT_FOUND:
                print(f"[BRAIN] Connection issue: {e.details()}")
            else:
                print(f"[BRAIN] Not found, falling back to local DB: {command_name}")

        # FALLBACK: Local Database (Legacy Flow)
        async with self.db_pool.acquire() as conn:
            # Attempt to retrieve pre-compiled bytecode from local table
            row_bc = await conn.fetchrow(
                "SELECT bytecode FROM avap_bytecode WHERE command_name = $1",
                command_name
            )
            
            # Always obtain the original code and interface to map properties
            row_func = await conn.fetchrow(
                "SELECT code, interface FROM obex_dapl_functions WHERE name = $1",
                command_name
            )
            
            if not row_func:
                raise ValueError(f"Command not found: {command_name}")

            try:
                interface = json.loads(row_func['interface']) if row_func['interface'] else []
            except:
                interface = []
            
            self.interface_cache[command_name] = interface

            if row_bc and row_bc['bytecode']:
                self.bytecode_cache[command_name] = row_bc['bytecode']
                return row_bc['bytecode'], interface
            
            # If there is no bytecode locally, compile and sign it
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
       
        import grpc
        import requests
        import tornado.web

        if cmd_name not in self.code_object_cache:
            # Unpack (HMAC)
            python_source = BytecodePacker.unpack(bytecode)
            # Code Object compilation (one time only)
            self.code_object_cache[cmd_name] = compile(python_source, f"<cmd:{cmd_name}>", "exec")
        
        code_obj = self.code_object_cache[cmd_name]
        # At this stage all commands arent heavies (is_heavy = False)
        is_heavy = False 

        # property mapping
        prop_dict = {str(i): v for i, v in enumerate(properties)}
        if interface:
            for i, param_def in enumerate(interface):
                key = param_def.get('item') or param_def.get('name') or str(i)
                if i < len(properties):
                    prop_dict[key] = properties[i]

        try:
            # Unpack signed binary
            python_code = BytecodePacker.unpack(bytecode)
        except Exception as e:
            print(f"[SECURITY ALERT] Bytecode processing error for {cmd_name}: {e}")
            raise RuntimeError(f"Integrity failure in command: {cmd_name}")

        # If/Loops bridge
        def process_step_sync(step_node):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self._execute_ast(step_node, context))

        # Namespace construction
        builtins_dict = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
        SAFE_BUILTINS = {**builtins_dict, 'print': print}
        namespace = {
            'task': {
                'properties': prop_dict, 
                'context': context.get("current_target"),
                'branches': node_full.get('branches', {}) if node_full else {},
                'sequence': node_full.get('sequence', []) if node_full else []
            },
            'self': ScriptBridge(self.conector, process_step_sync),
            'tornado': tornado, 
            'grpc': grpc, 
            'requests': requests,
            'json': json,
            're': re, 
            'uuid': uuid, 
            'os': os,
            '__builtins__': SAFE_BUILTINS
        }

        # Deciding if command is heavy or not
        
        if not is_heavy:
            # Only for logic commands (is_heavy=False)
            try:
                exec(code_obj, namespace)
            except Exception as e:
                raise e
        else:
            # For i/o commands
            loop = asyncio.get_running_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(thread_executor, lambda: exec(python_code, namespace)),
                    timeout=0.5 
                )
            except (asyncio.TimeoutError, queue.Full):
                worker_pid = os.getpid()
                print(f"[SECURITY] Killing script execution on Worker {worker_pid}: {cmd_name}")
                raise RuntimeError(f"Execution Timeout: Script '{cmd_name}' exceeded time limit.")
            except Exception as e:
                raise e

# HTTP HANDLERS
class ExecuteHandler(tornado.web.RequestHandler):


    def initialize(self, executor):
        self.executor = executor
    


    async def post(self):
        # Backpressure: Fail fast if no slot available within 200ms.
        self.executor.metrics["requests_total"] += 1
        start_time = time.perf_counter()
        try:
            await asyncio.wait_for(execution_semaphore.acquire(), timeout=0.5)
        except asyncio.TimeoutError:
            self.executor.metrics["rejects_concurrency"] += 1
            # Active denial for 99% latency
            self.set_status(503) # Service Unavailable
            return self.write({"success": False, "error": "Server Overloaded: Try again in miliseconds"})

        try:
            # Processing logic
            data = json.loads(self.request.body)
            script = data.get("script", "")
            variables = data.get("variables", {})
            
            if not script:
                raise ValueError("Script cannot be empty")
            
            # EXECUTION WATCHDOG: no one script can use more than 800ms of CPU
            try:
                result = await asyncio.wait_for(
                    self.executor.execute_script(script, variables, req=self),
                    timeout=0.8
                )
                self.executor.metrics["requests_success"] += 1
            except asyncio.TimeoutError:
                self.set_status(504) # Gateway Timeout
                self.executor.metrics["rejects_timeout"] += 1
                return self.write({"success": False, "error": "Script Execution Timeout (Isolation)"})

            # HTTP Status logic
            http_status = 200
            if "_status" in result['variables']:
                try:
                    val = int(result['variables']['_status'])
                    if 100 <= val <= 599: http_status = val
                except: pass

            self.set_status(http_status)
            self.write({
                "success": True,
                "result": result['results'],
                "variables": result['variables'],
                "logs": result['logs']
            })

        except Exception as e:
            self.set_status(400)
            self.executor.metrics["requests_error"] += 1
            self.write({"success": False, "error": str(e)})
        finally:
            # Liberation
            execution_semaphore.release()
            duration = (time.perf_counter() - start_time) * 1000
            self.executor.metrics["execution_time_ms"] += duration

class HealthHandler(tornado.web.RequestHandler):
    async def get(self):
        self.write({"status": "healthy", "service": "avap-server", "version": "1.0.33"})

class CompileHandler(tornado.web.RequestHandler):
    def initialize(self, executor):
        self.executor = executor
    
    async def post(self):
        
        try:
            data = json.loads(self.request.body)
            script = data.get("script", "")
            name = data.get("name")

            if not name or not script:
                    self.set_status(400)
                    return self.write({"error": "Missing name or script"})
            try:
                tree = ast.parse(script)
    
                optimizer = AVAPOptimizer()
                optimized_tree = optimizer.visit(tree)
                ast.fix_missing_locations(optimized_tree)
                final_script = ast.unparse(optimized_tree)
            except Exception as e:
                # Fallback: using original if optimization fails
                print(f"Optimization skipped: {e}")
                final_script = script

            # Packing
            bytecode = BytecodePacker.pack(final_script)
            
            script_hash = hashlib.sha256(final_script.encode()).hexdigest()
            
            async with self.executor.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO avap_bytecode (command_name, bytecode, version, compiled_at, source_hash)
                    VALUES ($1, $2, 1, NOW(), $3)
                    ON CONFLICT (command_name) 
                    DO UPDATE SET bytecode = $2, compiled_at = NOW(), source_hash = $3
                """, name, bytecode, script_hash)

            self.write({
                "status": "optimized & compiled",
                "name": name,
                "original_chars": len(script),
                "optimized_chars": len(final_script)
            })

        except Exception as e:
            self.set_status(500)
            self.write({"error": str(e)})

# Multi process configuration

def make_app(db_pool, executor):
    """Creating tornado application"""
    return tornado.web.Application([
        (r"/api/v1/execute", ExecuteHandler, dict(executor=executor)),
        (r"/api/v1/compile", CompileHandler, dict(executor=executor)),
        (r"/health", HealthHandler),
        (r"/", tornado.web.RedirectHandler, {"url": "/health"})
    ], 
    log_function=lambda x: None)

async def run_worker_instance(inherited_sockets):
    """Logic for each child process."""

    gc.set_threshold(50000, 15, 15)
    import nest_asyncio
    nest_asyncio.apply()
    
    worker_pid = os.getpid()
    
    try:
        # To ensure not all workers catch the CPU at same time
        import random
        await asyncio.sleep(random.uniform(0.05, 0.5))

        import asyncpg
        db_pool = await asyncpg.create_pool(options.db_url, min_size=1, max_size=5)
        
        executor = AVAPExecutor(db_pool)
        await executor.sync_full_catalog()
        executor.schedule_refresh()

        app = make_app(db_pool, executor)
        server = tornado.httpserver.HTTPServer(app)
        
        # Retry if kernel occupied
        try:
            server.add_sockets(inherited_sockets)
        except FileExistsError:
            await asyncio.sleep(0.5)
            server.add_sockets(inherited_sockets)
        
        print(f"Worker Ready [PID: {worker_pid}]")
        await asyncio.Event().wait()
        
    except Exception as e:
        print(f"Worker error {worker_pid}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import sys
    import os
    tornado.options.parse_command_line()
    
    # Master port
    try:
        shared_sockets = tornado.netutil.bind_sockets(options.port, backlog=8192)
        print(f"Master [PID: {os.getpid()}] bound port {options.port}")
    except Exception as e:
        print(f"Fatal bind port: {e}")
        sys.exit(1)

    # Process Fork
    try:
        # Launch child
        tornado.process.fork_processes(0)
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        print(f"Fork error: {e}")
        sys.exit(1)

    try:
        asyncio.run(run_worker_instance(shared_sockets))
    except KeyboardInterrupt:
        pass