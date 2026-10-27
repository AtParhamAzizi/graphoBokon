
from __future__ import annotations
import ast, builtins, fnmatch, hashlib, os, re
from dataclasses import dataclass, field
from pathlib import Path

from .language_readers import language_for, reader_for, should_read
DEFAULT_EXCLUDED={".git",".venv","venv","env","__pycache__","node_modules","dist","build","_site",".mypy_cache",".pytest_cache",".tox",".eggs",".idea",".vscode",".gradle",".next",".nuxt","coverage","target"}
def stable_id(prefix,value): return f"{prefix}:{hashlib.sha1(value.encode()).hexdigest()[:20]}"
@dataclass
class FileRecord:
 id:str; path:str; module:str; loc:int; source:str; symbols:list[str]=field(default_factory=list)
@dataclass
class SymbolRecord:
 id:str; kind:str; name:str; qualname:str; file_id:str; path:str; line:int; end_line:int; signature:str; docstring:str; decorators:list[str]; parent:str|None=None
class ProjectAnalyzer:
 def __init__(self,root,exclusions=None,max_files=2000,max_bytes=2000000):
  self.root=Path(root).expanduser().resolve(); self.exclusions=DEFAULT_EXCLUDED|set(exclusions or []); self.max_files=max_files; self.max_bytes=max_bytes
  self.files={}; self.symbols={}; self.module_to_file={}; self.trees={}; self.warnings=[]; self.edges=[]; self._edge_keys=set()
  self.bindings={}; self.parents={}; self.symbol_nodes={}; self.scoped_nodes={}; self.node_parents={}
 def _ignored(self,path):
  rel=path.relative_to(self.root).as_posix(); return any(p in self.exclusions for p in Path(rel).parts) or any(fnmatch.fnmatch(rel,p) for p in self.exclusions)
 def _module_name(self,path):
  parts=list(path.relative_to(self.root).with_suffix("").parts)
  if parts and parts[-1]=="__init__": parts.pop()
  return ".".join(parts)
 def _edge(self,source,target,relation,line,status="resolved",confidence=1.0,explanation="",evidence="",caller=None,callee=None):
  while source not in self.files and source not in self.symbols and source in self.parents:source=self.parents[source]
  while caller not in self.files and caller not in self.symbols and caller in self.parents:caller=self.parents[caller]
  key=(source,target,relation,line,evidence)
  if key in self._edge_keys:return
  path=self.symbols[source].path if source in self.symbols else self.files[source].path if source in self.files else ""
  self._edge_keys.add(key); self.edges.append({"id":stable_id("edge","|".join(map(str,key))),"source":source,"target":target,"type":relation,"line":line,"path":path,"status":status,"confidence":round(confidence,2),"explanation":explanation,"evidence":evidence,"caller":caller,"callee":callee})
 def _read_gitignore(self):
  try:return [x.strip() for x in (self.root/".gitignore").read_text(encoding="utf-8").splitlines() if x.strip() and not x.lstrip().startswith("#")]
  except (OSError,UnicodeDecodeError):return []
 def _gitignored(self,path,patterns):
  relative=path.relative_to(self.root); ignored=False
  for rule in patterns:
   negate=rule.startswith("!"); pattern=rule[1:] if negate else rule
   directory_only=pattern.endswith("/"); pattern=pattern.rstrip("/")
   anchored=pattern.startswith("/") or "/" in pattern; pattern=pattern.lstrip("/")
   candidates=[relative]+list(relative.parents)[:-1]
   for candidate in candidates:
    if directory_only and candidate==relative and not path.is_dir():continue
    value=candidate.as_posix() if anchored else candidate.name
    if fnmatch.fnmatchcase(value,pattern):ignored=not negate; break
  return ignored
 def _signature(self,node):
  try:return ast.unparse(node.args)
  except Exception:return ""
 def _decorators(self,node):
  out=[]
  for item in getattr(node,"decorator_list",[]):
   try:out.append(ast.unparse(item))
   except Exception:out.append(type(item).__name__)
  return out
 def _snippet(self,file,line,end_line):
  lines=file.source.splitlines(); return "\n".join(f"{n:>4} | {lines[n-1]}" for n in range(max(1,line),min(len(lines),end_line)+1))
 def _parse_files(self,progress):
  patterns=self._read_gitignore(); candidates=[]
  is_junction=getattr(os.path,"isjunction",lambda path:False)
  for directory,folders,filenames in os.walk(self.root,followlinks=False):
   folders[:]=[name for name in folders if not (Path(directory)/name).is_symlink() and not is_junction(Path(directory)/name) and not self._ignored(Path(directory)/name) and not self._gitignored(Path(directory)/name,patterns)]
   for name in filenames:
    path=Path(directory)/name
    try:
     if path.is_symlink() or not path.resolve().is_relative_to(self.root) or self._ignored(path) or self._gitignored(path,patterns):continue
     if should_read(path):candidates.append(path)
    except (OSError,ValueError):continue
  candidates.sort()
  if len(candidates)>self.max_files:self.warnings.append({"code":"FILE_LIMIT","message":f"Only the first {self.max_files} supported files were analyzed."}); candidates=candidates[:self.max_files]
  for i,path in enumerate(candidates):
   rel=path.relative_to(self.root).as_posix()
   if progress:progress(i,len(candidates),f"Parsing {rel}")
   try:
    if path.stat().st_size>self.max_bytes:self.warnings.append({"code":"FILE_TOO_LARGE","message":f"Skipped {rel} because it exceeds {self.max_bytes} bytes."});continue
    source=path.read_text(encoding="utf-8")
    if "\x00" in source:self.warnings.append({"code":"BINARY_FILE","message":f"Skipped {rel} because it contains binary data."});continue
    reader=reader_for(path)
    tree=reader.parse_source(source,rel) if reader and reader.parse else None
   except SyntaxError as e:self.warnings.append({"code":"SYNTAX_ERROR","message":f"{rel}:{e.lineno}: {e.msg}"});continue
   except (OSError,UnicodeDecodeError) as e:self.warnings.append({"code":"READ_ERROR","message":f"{rel}: {e}"});continue
   module=self._module_name(path) if tree is not None else path.stem
   fid=stable_id("file",rel); self.files[fid]=FileRecord(fid,rel,module,len(source.splitlines()),source)
   if tree is not None:
    self.module_to_file[module]=fid; self.trees[fid]=tree; self._collect_symbols(self.files[fid],tree)
 def _collect_symbols(self,file,tree):
  self.bindings[file.id]={}; self.parents[file.id]=None; self.scoped_nodes[file.id]=[]
  def visit(node,scope,prefix):
   self.scoped_nodes[file.id].append((node,scope))
   for child in ast.iter_child_nodes(node):self.node_parents[id(child)]=node
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
    qual=f"{prefix}.{node.name}" if prefix else node.name; sid=stable_id("symbol",f"{file.path}:{qual}:{node.lineno}")
    parent=self.symbols.get(scope); is_class=isinstance(node,ast.ClassDef)
    kind="class" if is_class else "async_function" if isinstance(node,ast.AsyncFunctionDef) else "method" if parent and parent.kind=="class" else "function"
    symbol=SymbolRecord(sid,kind,node.name,qual,file.id,file.path,node.lineno,getattr(node,"end_lineno",node.lineno),"" if is_class else self._signature(node),ast.get_docstring(node) or "",self._decorators(node),parent.id if parent else None)
    self.symbols[sid]=symbol; self.symbol_nodes[sid]=node; file.symbols.append(sid); self.parents[sid]=scope; self.bindings[sid]={}; self.bindings[scope][node.name]=("target",sid)
    self._edge(scope,sid,"CONTAINS",node.lineno,evidence=f"{'class' if is_class else 'def'} {node.name}")
    if not is_class:
     arguments=node.args.posonlyargs+node.args.args+node.args.kwonlyargs
     arguments += [argument for argument in (node.args.vararg,node.args.kwarg) if argument]
     for argument in arguments:self.bindings[sid][argument.arg]=("annotation",argument.annotation,scope) if argument.annotation else ("unknown",)
     positional=node.args.posonlyargs+node.args.args
     if parent and parent.kind=="class" and positional and not any(decorator.split(".")[-1]=="staticmethod" for decorator in symbol.decorators):self.bindings[sid][positional[0].arg]=("target",scope)
    for child in ast.iter_child_nodes(node):
     if child not in node.body:visit(child,scope,prefix)
    for child in node.body:visit(child,sid,qual)
   elif isinstance(node,(ast.Lambda,ast.ListComp,ast.SetComp,ast.DictComp,ast.GeneratorExp)):
    inner=stable_id("scope",f"{file.path}:{type(node).__name__}:{node.lineno}:{node.col_offset}"); self.parents[inner]=scope; self.bindings[inner]={}
    if isinstance(node,ast.Lambda):
     arguments=node.args.posonlyargs+node.args.args+node.args.kwonlyargs+[argument for argument in (node.args.vararg,node.args.kwarg) if argument]
     for argument in arguments:self.bindings[inner][argument.arg]=("unknown",)
     visit(node.args,scope,prefix); visit(node.body,inner,prefix)
    else:
     for index,generator in enumerate(node.generators):
      visit(generator.iter,scope if index==0 else inner,prefix)
      for item in ast.walk(generator.target):
       if isinstance(item,ast.Name):self.bindings[inner][item.id]=("unknown",)
      visit(generator.target,inner,prefix)
      for condition in generator.ifs:visit(condition,inner,prefix)
     for expression in (node.key,node.value) if isinstance(node,ast.DictComp) else (node.elt,):visit(expression,inner,prefix)
   else:
    for child in ast.iter_child_nodes(node):visit(child,scope,prefix)
  visit(tree,file.id,file.module)
 def _import_base(self,file,node):
  if not node.level:return node.module or ""
  package=[part for part in file.module.split(".") if part] if Path(file.path).name=="__init__.py" else file.module.split(".")[:-1]
  package=package[:len(package)-node.level+1] if node.level<=len(package)+1 else []
  if not package and (self.root/"__init__.py").is_file() and self.root.name.isidentifier():package=[self.root.name]
  return ".".join(package+([node.module] if node.module else []))
 def _collect_imports(self):
  imports=[]
  for fid,scoped_nodes in self.scoped_nodes.items():
   file=self.files[fid]
   for node,scope in scoped_nodes:
    if isinstance(node,ast.Import):
     for alias in node.names:
      local=alias.asname or alias.name.split(".")[0]; self.bindings[scope][local]=("import",alias.name if alias.asname else local); imports.append((scope,node,alias.name))
    elif isinstance(node,ast.ImportFrom):
     base=self._import_base(file,node)
     for alias in node.names:
      path=".".join(part for part in (base,alias.name) if part)
      if alias.name=="*":
       imports.append((scope,node,base)); self.warnings.append({"code":"WILDCARD_IMPORT","message":f"{file.path}:{node.lineno}: wildcard import names are not resolved."}); continue
      self.bindings[scope][alias.asname or alias.name]=("import",path); imports.append((scope,node,path))
  self.pending_imports=imports
 def _collect_import_edges(self):
  for scope,node,path in self.pending_imports:
   target=self._resolve_path(path,set()) or self._module_dependency(path); local=target in self.files or target in self.symbols
   self._edge(scope,target or f"external:module:{path}","IMPORTS",node.lineno,"resolved" if local else "inferred",1 if local else .9,"" if local else "Import points outside the analyzed project.",ast.unparse(node))
 def _collect_bindings(self):
  for scoped_nodes in self.scoped_nodes.values():
   for node,scope in scoped_nodes:
    if isinstance(node,(ast.Assign,ast.AnnAssign,ast.NamedExpr)):
     targets=node.targets if isinstance(node,ast.Assign) else [node.target]
     binding=("value",node.value,scope) if node.value is not None else ("annotation",node.annotation,scope)
     for target in targets:
      if isinstance(target,ast.Name):self.bindings[scope][target.id]=binding
      elif isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name):
       receiver=self.bindings[scope].get(target.value.id,())
       if receiver and receiver[0]=="target" and self.symbols.get(receiver[1]) and self.symbols[receiver[1]].kind=="class":self.bindings[receiver[1]][target.attr]=binding
      elif isinstance(target,(ast.Tuple,ast.List)):
       for item in ast.walk(target):
        if isinstance(item,ast.Name):self.bindings[scope][item.id]=("unknown",)
    elif isinstance(node,(ast.With,ast.AsyncWith)):
     for item in node.items:
      if isinstance(item.optional_vars,ast.Name):self.bindings[scope][item.optional_vars.id]=("value",item.context_expr,scope)
    elif isinstance(node,(ast.For,ast.AsyncFor,ast.ExceptHandler)):
     targets=[node.target] if isinstance(node,(ast.For,ast.AsyncFor)) else []
     if isinstance(node,ast.ExceptHandler) and node.name:self.bindings[scope][node.name]=("unknown",)
     for target in targets:
      if target:
       for item in ast.walk(target):
        if isinstance(item,ast.Name):self.bindings[scope][item.id]=("unknown",)
 def _resolve_binding(self,scope,name,seen):
  key=(scope,name)
  if key in seen:return None
  binding=self.bindings.get(scope,{}).get(name)
  if not binding:return None
  seen=seen|{key}
  if binding[0]=="target":return binding[1]
  if binding[0]=="import":return self._resolve_path(binding[1],seen)
  if binding[0]=="value":return self._resolve_expr(binding[1],binding[2],seen)
  if binding[0]=="annotation":return self._resolve_annotation(binding[1],binding[2],seen)
  return None
 def _resolve_name(self,scope,name,seen):
  while scope:
   if name in self.bindings.get(scope,{}):return self._resolve_binding(scope,name,seen)
   scope=self.parents.get(scope)
   while scope in self.symbols and self.symbols[scope].kind=="class":scope=self.parents.get(scope)
  return None
 def _resolve_path(self,path,seen):
  if path in self.module_to_file:return self.module_to_file[path]
  parts=path.split(".")
  for length in range(len(parts)-1,0,-1):
   module=".".join(parts[:length])
   if module in self.module_to_file:
    target=self.module_to_file[module]
    for member in parts[length:]:
     target=self._resolve_member(target,member,seen)
     if not target:return None
    return target
  return f"external:module:{path}"
 def _module_dependency(self,path):
  parts=path.split(".")
  for length in range(len(parts),0,-1):
   module=".".join(parts[:length])
   if module in self.module_to_file:return self.module_to_file[module]
  return None
 def _reference_target(self,node,scope):
  target=self._resolve_expr(node,scope)
  if target:return target
  if isinstance(node,ast.Name):
   while scope:
    if node.id in self.bindings.get(scope,{}):
     binding=self.bindings[scope][node.id]
     return self._module_dependency(binding[1]) if binding[0]=="import" else None
    scope=self.parents.get(scope)
    while scope in self.symbols and self.symbols[scope].kind=="class":scope=self.parents.get(scope)
  if isinstance(node,ast.Attribute):
   owner=self._resolve_expr(node.value,scope)
   if owner in self.files and node.attr in self.bindings[owner]:return owner
  return None
 def _bases(self,class_id,seen):
  node=self.symbol_nodes.get(class_id)
  if not isinstance(node,ast.ClassDef):return []
  return [target for base in node.bases if (target:=self._resolve_expr(base.value if isinstance(base,ast.Subscript) else base,self.parents[class_id],seen))]
 def _resolve_member(self,target,name,seen):
  if not target:return None
  key=(target,name)
  if key in seen:return None
  if target in self.files:
   module=self.files[target].module; path=f"{module}.{name}" if module else name
   return self._resolve_binding(target,name,seen) if name in self.bindings[target] else self.module_to_file.get(path)
  if target in self.symbols and self.symbols[target].kind=="class":
   if name in self.bindings[target]:return self._resolve_binding(target,name,seen)
   for base in self._bases(target,seen|{key}):
    member=self._resolve_member(base,name,seen|{key})
    if member:return member
  if target.startswith(("external:module:","external:symbol:")):
   path=f"{target.split(':',2)[2]}.{name}"
   return self.module_to_file.get(path) or f"external:symbol:{path}"
  return None
 def _resolve_annotation(self,node,scope,seen):
  if isinstance(node,ast.Constant) and isinstance(node.value,str):
   try:node=ast.parse(node.value,mode="eval").body
   except (SyntaxError,ValueError):return None
  return self._resolve_expr(node,scope,seen)
 def _resolve_expr(self,node,scope,seen=None):
  if node is None:return None
  seen=set() if seen is None else seen
  if len(seen)>50:return None
  if isinstance(node,ast.Name):return self._resolve_name(scope,node.id,seen)
  if isinstance(node,ast.Attribute):return self._resolve_member(self._resolve_expr(node.value,scope,seen),node.attr,seen)
  if isinstance(node,ast.Await):return self._resolve_expr(node.value,scope,seen)
  if isinstance(node,ast.Call):
   if isinstance(node.func,ast.Name) and node.func.id=="super":
    owner=scope
    while owner in self.symbols and self.symbols[owner].kind!="class":owner=self.parents[owner]
    bases=self._bases(owner,seen)
    return bases[0] if bases else None
   target=self._resolve_expr(node.func,scope,seen)
   if target in self.symbols:
    if self.symbols[target].kind=="class":return target
    key=("return",target)
    if key not in seen:return self._resolve_annotation(getattr(self.symbol_nodes[target],"returns",None),self.parents[target],seen|{key})
   if target and target.startswith("external:") and target.split(".")[-1][:1].isupper():return target
  return None
 def _relationship(self,scope,target,relation,node,evidence=None):
  if not target:return
  local=target in self.symbols or target in self.files
  self._edge(scope,target,relation,getattr(node,"lineno",1),"resolved" if local else "inferred",1 if local else .85,"" if local else "External dependency identified from static syntax.",evidence or ast.unparse(node),scope,target)
 def _collect_definitions(self):
  for sid,node in self.symbol_nodes.items():
   scope=self.parents[sid]
   for decorator in node.decorator_list:self._relationship(sid,self._resolve_expr(decorator.func if isinstance(decorator,ast.Call) else decorator,scope),"DECORATED_BY",decorator)
   if isinstance(node,ast.ClassDef):
    for base in node.bases:
     target=self._resolve_expr(base.value if isinstance(base,ast.Subscript) else base,scope)
     self._relationship(sid,target or f"external:class:{ast.unparse(base)}","INHERITS",base)
    for child in self.bindings[sid].values():
     if child[0]!="target" or child[1] not in self.symbols:continue
     method=self.symbols[child[1]]
     if method.kind=="class":continue
     for base in self._bases(sid,set()):
      target=self._resolve_member(base,method.name,set())
      if target in self.symbols:self._relationship(method.id,target,"OVERRIDES",self.symbol_nodes[method.id])
 def _type_relationships(self,scope,annotation):
  original=annotation
  if isinstance(annotation,ast.Constant) and isinstance(annotation.value,str):
   try:annotation=ast.parse(annotation.value,mode="eval").body
   except (SyntaxError,ValueError):return
  def visit(node):
   if isinstance(node,ast.Subscript) and self._resolve_expr(node.value,scope) in {"external:module:typing.Literal","external:module:typing_extensions.Literal","external:symbol:typing.Literal","external:symbol:typing_extensions.Literal"}:
    visit(node.value)
   elif isinstance(node,(ast.Name,ast.Attribute)):
    self._relationship(scope,self._reference_target(node,scope),"USES_TYPE",original)
   elif isinstance(node,ast.Constant) and isinstance(node.value,str) and node is not annotation:self._type_relationships(scope,node)
   else:
    for child in ast.iter_child_nodes(node):visit(child)
  visit(annotation)
 def _collect_behavior(self):
  http={"requests","httpx","aiohttp"}; routes={"get","post","put","patch","delete","options","head","route","api_route","websocket"}; builtins_names=set(dir(builtins))
  ignored_references=set(); definition_ids={id(node):sid for sid,node in self.symbol_nodes.items()}
  for sid,node in self.symbol_nodes.items():
   metadata=list(node.decorator_list)+list(getattr(node,"bases",[])); annotations=[]
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
    arguments=node.args.posonlyargs+node.args.args+node.args.kwonlyargs+[argument for argument in (node.args.vararg,node.args.kwarg) if argument]
    annotations=[argument.annotation for argument in arguments if argument.annotation]
    if node.returns:annotations.append(node.returns)
   for annotation in annotations:self._type_relationships(sid,annotation)
   for expression in metadata+annotations:ignored_references.update(id(child) for child in ast.walk(expression))
  for scoped_nodes in self.scoped_nodes.values():
   for node,scope in scoped_nodes:
    if isinstance(node,ast.AnnAssign):
     self._type_relationships(scope,node.annotation); ignored_references.update(id(child) for child in ast.walk(node.annotation))
    if isinstance(node,ast.Raise) and node.exc:
     expression=node.exc.func if isinstance(node.exc,ast.Call) else node.exc; target=self._resolve_expr(expression,scope)
     if not target and isinstance(expression,ast.Name) and isinstance(getattr(builtins,expression.id,None),type) and issubclass(getattr(builtins,expression.id),BaseException):target=f"external:class:{expression.id}"
     self._relationship(scope,target,"RAISES",node)
    if isinstance(node,ast.Call):
     expr,evidence=ast.unparse(node.func),ast.unparse(node); target=self._resolve_expr(node.func,scope); canonical=target.split(":",2)[2] if target and target.startswith("external:") else ""
     if target in self.files:target=None
     if not target:
      dependency=self._reference_target(node.func.value if isinstance(node.func,ast.Attribute) else node.func,scope)
      if dependency in self.files:self._relationship(scope,dependency,"REFERENCES",node)
     if canonical.split(".")[0] in http and canonical.split(".")[-1] in routes|{"request"}:
      self._edge(scope,f"external:http:{canonical}","HTTP_REQUEST",node.lineno,"inferred",.88,"Recognized requests/httpx/aiohttp client call.",evidence,scope,canonical)
     parent=self.node_parents.get(id(node)); owner=definition_ids.get(id(parent)) if isinstance(parent,(ast.FunctionDef,ast.AsyncFunctionDef)) and node in parent.decorator_list else None
     if expr.split(".")[-1] in routes and node.args and (owner or expr.split(".")[-1] in {"route","api_route"}):
      try:route=ast.literal_eval(node.args[0])
      except (ValueError,TypeError):route=None
      if isinstance(route,str):self._edge(owner or scope,f"external:route:{route}","DEFINES_ROUTE",node.lineno,"inferred",.86,"Framework-style route registration or decorator.",evidence,owner or scope,route)
     if target:
      self._relationship(scope,target,"CALLS",node)
      if target in self.symbols and self.symbols[target].kind=="class":self._relationship(scope,target,"INSTANTIATES",node)
     elif not (isinstance(node.func,ast.Name) and node.func.id in builtins_names):self._edge(scope,f"unresolved:{expr}","CALLS",node.lineno,"unresolved",.2,"Dynamic dispatch or local scope could not be resolved statically.",evidence,scope,expr)
    elif isinstance(node,(ast.Name,ast.Attribute)) and isinstance(node.ctx,ast.Load) and id(node) not in ignored_references:
     parent=self.node_parents.get(id(node))
     if isinstance(parent,ast.Attribute) and parent.value is node or isinstance(parent,ast.Call) and parent.func is node:continue
     target=self._reference_target(node,scope)
     if target in self.symbols or target in self.files:self._relationship(scope,target,"REFERENCES",node)
 def _aggregate(self,edges):
  result={}
  for e in edges:
   source=self.symbols[e["source"]].file_id if e["source"] in self.symbols else e["source"]; target=self.symbols[e["target"]].file_id if e["target"] in self.symbols else e["target"]
   if source==target or source not in self.files:continue
   key=(source,target,e["type"]); item=result.setdefault(key,{"id":stable_id("file-edge","|".join(key)),"source":source,"target":target,"type":e["type"],"count":0,"status":e["status"],"confidence":e["confidence"],"evidence":[]}); item["count"]+=1; item["confidence"]=min(item["confidence"],e["confidence"])
   if len(item["evidence"])<20:item["evidence"].append({"line":e["line"],"path":e["path"],"evidence":e["evidence"],"relationship_id":e["id"]})
  return list(result.values())
 def _collect_text_relationships(self):
  """Create file-level import/include edges for non-Python languages."""
  by_name={}
  for fid,file in self.files.items():
   path=Path(file.path)
   for key in {path.name,path.stem,file.module,path.as_posix(),path.with_suffix('').as_posix()}:
    if key:by_name.setdefault(key.replace('\\','/'),fid)
  patterns=(re.compile(r"^\s*(?:import|export)\s+(?:type\s+)?[^'\"]*?from\s*['\"]([^'\"]+)['\"]|^\s*import\s*['\"]([^'\"]+)['\"]"),re.compile(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)"),re.compile(r"^\s*(?:#\s*include|include)\s*[<\"]([^>\"]+)[>\"]"),re.compile(r"^\s*(?:using|import)\s+([A-Za-z_][\w.]*)\s*;?"),re.compile(r"^\s*use\s+([A-Za-z_][\w:]*)(?:::\*)?\s*;?"))
  for fid,file in self.files.items():
   if fid in self.trees:continue
   for line_no,line in enumerate(file.source.splitlines(),1):
    for pattern in patterns:
     match=pattern.search(line)
     if not match:continue
     raw=next((value for value in match.groups() if value),"")
     normalized=raw.replace('\\','/').removeprefix('./')
     target=by_name.get(normalized) or by_name.get(Path(normalized).name)
     if not target:
      stem=Path(normalized).stem
      target=next((candidate for key,candidate in by_name.items() if Path(key).stem==stem),None)
     target=target or f"external:module:{raw}"
     self._edge(fid,target,"IMPORTS",line_no,"resolved" if target in self.files else "inferred",1 if target in self.files else .8,"Lexical import/include detected.",line.strip())
 def scan(self,progress=None):
  if not self.root.exists() or not self.root.is_dir():raise ValueError("Directory does not exist or is not a directory")
  self._parse_files(progress)
  package_root=(self.root/"__init__.py").is_file() and self.root.name.isidentifier()
  suffixes={}
  for file in self.files.values():
   parts=file.module.split(".") if file.module else []
   for start in range(1,len(parts)):suffixes.setdefault(".".join(parts[start:]),set()).add(file.id)
  for alias,owners in suffixes.items():
   if len(owners)==1:self.module_to_file.setdefault(alias,next(iter(owners)))
  for file in self.files.values():
   if file.path.startswith("src/"):self.module_to_file.setdefault(file.module.removeprefix("src."),file.id)
   if package_root:self.module_to_file.setdefault(".".join(part for part in (self.root.name,file.module) if part),file.id)
  self._collect_imports(); self._collect_bindings(); self._collect_import_edges(); self._collect_definitions(); self._collect_behavior(); self._collect_text_relationships()
  nodes=[{"id":f.id,"kind":"file","label":f.path,"path":f.path,"module":f.module,"language":language_for(Path(f.path)),"loc":f.loc,"symbol_count":len(f.symbols)} for f in self.files.values()]
  nodes += [{"id":s.id,"kind":s.kind,"label":s.name,"qualname":s.qualname,"path":s.path,"file_id":s.file_id,"line":s.line,"end_line":s.end_line,"signature":s.signature,"docstring":s.docstring,"decorators":s.decorators,"parent":s.parent,"snippet":self._snippet(self.files[s.file_id],s.line,s.end_line)} for s in self.symbols.values()]
  external={e["target"] for e in self.edges if str(e["target"]).startswith(("external:","unresolved:"))}
  for entity in sorted(external):
   parts=entity.split(":",2); kind=parts[1] if len(parts)>1 else "unknown"; label=parts[2] if len(parts)>2 else parts[-1]; nodes.append({"id":entity,"kind":"external","external_type":kind,"label":label})
  file_edges=self._aggregate(self.edges)
  return {"schema_version":"1.3","root":str(self.root),"project":{"is_python":any(Path(file.path).suffix.lower()==".py" for file in self.files.values()),"languages":sorted({language_for(Path(file.path)) for file in self.files.values()}),"metadata":[n for n in ("pyproject.toml","setup.py","requirements.txt","package.json","Cargo.toml","go.mod","pom.xml","build.gradle") if (self.root/n).exists()]},"nodes":nodes,"edges":self.edges,"file_edges":file_edges,"warnings":self.warnings,"stats":{"python_files":sum(Path(file.path).suffix.lower()==".py" for file in self.files.values()),"files":len(self.files),"indexed_files":len(self.files),"symbols":len(self.symbols),"edges":len(self.edges),"file_edges":len(file_edges)},"limitations":["Python files receive static AST symbol and relationship analysis; other readable project files are indexed and available for source inspection.","Static AST analysis cannot fully recover dynamic dispatch, reflection, monkey-patching, generated code, or runtime decorator behavior.","Assignments, receiver types, and inherited methods use static bindings; conditional rebinding and multiple-inheritance runtime order may differ.","Wildcard imports are reported but their exported names are not guessed.","HTTP requests remain separate from local CALLS and are not mapped to local handlers without explicit static evidence."]}
def analyze_directory(path,exclusions=None,progress=None):return ProjectAnalyzer(path,exclusions).scan(progress)


