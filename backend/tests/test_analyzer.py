import tempfile
import textwrap
import unittest
from pathlib import Path
from backend.analyzer import analyze_directory

class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.demo = Path(__file__).parents[2] / "demo_project"

    def analyze_sources(self, sources):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source in sources.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(textwrap.dedent(source), encoding="utf-8")
            return analyze_directory(directory)

    def relationships(self, result, relation):
        labels = {node["id"]: node.get("qualname", node["label"]) for node in result["nodes"]}
        return {(labels[edge["source"]], labels[edge["target"]]) for edge in result["edges"] if edge["type"] == relation}

    def test_dotted_imports_aliases_and_package_reexports(self):
        result = self.analyze_sources({
            "pkg/__init__.py": "from .worker import execute\n",
            "pkg/worker.py": "def execute(): pass\n",
            "main.py": """
                import pkg.worker
                import pkg.worker as renamed
                from pkg import worker as module
                from pkg import execute as public
                def run():
                    pkg.worker.execute()
                    renamed.execute()
                    module.execute()
                    public()
            """,
        })
        calls = [edge for edge in result["edges"] if edge["type"] == "CALLS"]
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(edge["status"] == "resolved" for edge in calls))
        self.assertEqual(self.relationships(result, "CALLS"), {("main.run", "pkg.worker.execute")})

    def test_instance_methods_inheritance_overrides_and_super(self):
        result = self.analyze_sources({
            "base.py": "class Base:\n    def run(self): pass\n",
            "child.py": """
                from base import Base
                class Child(Base):
                    def run(self):
                        return super().run()
                    def invoke(self):
                        return self.run()
                def make() -> Child:
                    return Child()
                def use(worker: 'Child'):
                    worker.invoke()
                    instance = Child()
                    instance.run()
                    make().invoke()
            """,
        })
        calls = self.relationships(result, "CALLS")
        self.assertTrue({("child.Child.run", "base.Base.run"), ("child.Child.invoke", "child.Child.run"), ("child.use", "child.Child.invoke"), ("child.use", "child.Child.run")} <= calls)
        self.assertIn(("child.Child", "base.Base"), self.relationships(result, "INHERITS"))
        self.assertIn(("child.Child.run", "base.Base.run"), self.relationships(result, "OVERRIDES"))
        self.assertIn(("child.use", "child.Child"), self.relationships(result, "INSTANTIATES"))
        self.assertIn(("child.use", "child.Child"), self.relationships(result, "USES_TYPE"))

    def test_nested_scope_containment_and_method_name_collisions(self):
        result = self.analyze_sources({"scopes.py": """
            def helper(): pass
            class First:
                def helper(self): pass
                def run(self): self.helper()
            class Second:
                def helper(self): pass
                def run(self): self.helper()
            def outer():
                def helper(): pass
                helper()
            def shadow(helper): helper()
            def caller(): helper()
            try:
                def guarded(): helper()
            except Exception:
                pass
        """})
        calls = self.relationships(result, "CALLS")
        self.assertTrue({("scopes.First.run", "scopes.First.helper"), ("scopes.Second.run", "scopes.Second.helper"), ("scopes.outer", "scopes.outer.helper"), ("scopes.caller", "scopes.helper"), ("scopes.guarded", "scopes.helper")} <= calls)
        self.assertNotIn(("scopes.shadow", "scopes.helper"), calls)
        contains = self.relationships(result, "CONTAINS")
        self.assertIn(("scopes.First", "scopes.First.run"), contains)
        self.assertIn(("scopes.outer", "scopes.outer.helper"), contains)
        self.assertTrue(all(node["kind"] != "file" for node in result["nodes"] if node["id"] in {edge["target"] for edge in result["edges"] if edge["type"] == "CALLS"}))

    def test_callback_type_decorator_exception_and_file_relationships(self):
        result = self.analyze_sources({
            "types.py": """
                class Item: pass
                class Problem(Exception): pass
                def decorate(function): return function
                def callback(): pass
            """,
            "main.py": """
                from types import Item, Problem, decorate, callback
                @decorate
                def run(value: Item) -> list['Item']:
                    handler = callback
                    handler()
                    sorted([], key=callback)
                    raise Problem()
            """,
        })
        self.assertIn(("main.run", "types.decorate"), self.relationships(result, "DECORATED_BY"))
        self.assertIn(("main.run", "types.callback"), self.relationships(result, "REFERENCES"))
        self.assertIn(("main.run", "types.callback"), self.relationships(result, "CALLS"))
        self.assertIn(("main.run", "types.Item"), self.relationships(result, "USES_TYPE"))
        self.assertIn(("main.run", "types.Problem"), self.relationships(result, "RAISES"))
        file_ids = {node["path"]: node["id"] for node in result["nodes"] if node["kind"] == "file"}
        for relation in ("DECORATED_BY", "REFERENCES", "CALLS", "USES_TYPE", "RAISES"):
            aggregate = next(edge for edge in result["file_edges"] if edge["type"] == relation and edge["source"] == file_ids["main.py"] and edge["target"] == file_ids["types.py"])
            self.assertGreater(aggregate["count"], 0)
            self.assertEqual(aggregate["evidence"][0]["path"], "main.py")
        node_ids = {node["id"] for node in result["nodes"]}
        self.assertTrue(all(edge["source"] in node_ids and edge["target"] in node_ids for edge in result["edges"]))
        self.assertEqual(result["stats"]["edges"], len(result["edges"]))

    def test_local_imports_do_not_leak_into_other_functions(self):
        result = self.analyze_sources({
            "worker.py": "def execute(): pass\n",
            "main.py": """
                def local():
                    from worker import execute
                    execute()
                def other(): execute()
            """,
        })
        self.assertIn(("main.local", "worker.execute"), self.relationships(result, "CALLS"))
        self.assertNotIn(("main.other", "worker.execute"), self.relationships(result, "CALLS"))

    def test_http_aliases_client_instances_and_handler_ownership(self):
        result = self.analyze_sources({"web.py": """
            import httpx as client
            from httpx import AsyncClient as Client
            from fastapi import FastAPI
            app = FastAPI()
            @app.get('/items')
            async def handler():
                client.get('https://example.com')
                async with Client() as session:
                    await session.get('https://example.com/items')
        """})
        http = [edge for edge in result["edges"] if edge["type"] == "HTTP_REQUEST"]
        self.assertEqual(len(http), 2)
        handler = next(node for node in result["nodes"] if node.get("qualname") == "web.handler")
        self.assertTrue(all(edge["source"] == handler["id"] for edge in http))
        self.assertIn(("web.handler", "/items"), self.relationships(result, "DEFINES_ROUTE"))
        self.assertIn(("web.handler", "fastapi.FastAPI.get"), self.relationships(result, "DECORATED_BY"))

    def test_unknown_attribute_calls_and_non_callable_literals(self):
        result = self.analyze_sources({"main.py": """
            class Service:
                def run(self): pass
            name = 'Service'
            def use(dynamic):
                dynamic.missing()
                name.run()
        """})
        self.assertFalse(any(target == "main.Service.run" for source, target in self.relationships(result, "CALLS")))
        unresolved = [edge for edge in result["edges"] if edge["type"] == "CALLS" and edge["status"] == "unresolved"]
        self.assertEqual(len(unresolved), 2)

    def test_lambda_and_comprehension_names_do_not_create_false_calls(self):
        result = self.analyze_sources({"main.py": """
            def callback(): pass
            def use(values):
                wrapped = lambda callback: callback()
                [callback() for callback in values]
                callback()
        """})
        calls = [edge for edge in result["edges"] if edge["type"] == "CALLS" and edge["status"] == "resolved"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.relationships(result, "CALLS") & {("main.use", "main.callback")}, {("main.use", "main.callback")})

    def test_cyclic_aliases_and_unknown_wildcards_remain_safe(self):
        result = self.analyze_sources({
            "first.py": "from second import alias\n",
            "second.py": "from first import alias\n",
            "main.py": "from first import *\nfrom first import alias\nalias()\n",
        })
        self.assertTrue(any(warning["code"] == "WILDCARD_IMPORT" for warning in result["warnings"]))
        self.assertTrue(any(edge["type"] == "CALLS" and edge["status"] == "unresolved" for edge in result["edges"]))

    def test_imported_constants_link_to_files_without_calling_module_nodes(self):
        result = self.analyze_sources({
            "config.py": "FLAG = True\nSETTINGS = {}\n",
            "main.py": """
                import config
                from config import FLAG, SETTINGS
                def run():
                    print(FLAG, config.FLAG)
                    SETTINGS.get('name')
                    config()
            """,
        })
        self.assertIn(("main.run", "config.py"), self.relationships(result, "REFERENCES"))
        self.assertEqual(sum(edge["type"] == "IMPORTS" and edge["status"] == "resolved" for edge in result["edges"]), 2)
        self.assertNotIn(("main.run", "config.py"), self.relationships(result, "CALLS"))
        self.assertTrue(any(edge["type"] == "CALLS" and edge["status"] == "unresolved" for edge in result["edges"]))

    def test_src_layout_imports_resolve_to_project_symbols(self):
        result = self.analyze_sources({
            "src/pkg/__init__.py": "from .worker import execute\n",
            "src/pkg/worker.py": "def execute(): pass\n",
            "main.py": "from pkg import execute\ndef run(): execute()\n",
        })
        self.assertIn(("main.run", "src.pkg.worker.execute"), self.relationships(result, "CALLS"))

    def test_instance_attributes_inherited_methods_and_classmethods(self):
        result = self.analyze_sources({"main.py": """
            class Worker:
                async def execute(self): pass
                @classmethod
                def create(cls): return cls()
            class Child(Worker): pass
            class Service:
                def __init__(self): self.worker = Child()
                async def run(self): await self.worker.execute()
            def use(): Worker.create()
        """})
        self.assertIn(("main.Service.run", "main.Worker.execute"), self.relationships(result, "CALLS"))
        self.assertIn(("main.use", "main.Worker.create"), self.relationships(result, "CALLS"))
        self.assertIn(("main.Worker.create", "main.Worker"), self.relationships(result, "INSTANTIATES"))

    def test_scanning_package_directory_preserves_relative_reexports(self):
        result = self.analyze_sources({
            "__init__.py": "from .worker import Worker\n",
            "worker.py": "class Worker:\n    def execute(self): pass\n",
            "api.py": "from . import Worker\ndef run(): Worker().execute()\n",
        })
        self.assertIn(("api.run", "worker.Worker.execute"), self.relationships(result, "CALLS"))

    def test_literal_annotation_values_are_not_forward_type_references(self):
        result = self.analyze_sources({"main.py": """
            from typing import Literal
            class Token: pass
            def use(value: Literal['Token']): pass
        """})
        self.assertNotIn(("main.use", "main.Token"), self.relationships(result, "USES_TYPE"))

    def test_demo_relationship_types_and_resolution(self):
        result = analyze_directory(str(self.demo))
        self.assertGreaterEqual(result["stats"]["files"], 25)
        self.assertGreaterEqual(result["stats"]["symbols"], 90)
        kinds = {edge["type"] for edge in result["edges"]}
        expected_types = {
            "CONTAINS", "IMPORTS", "CALLS", "INSTANTIATES", "REFERENCES",
            "USES_TYPE", "DECORATED_BY", "INHERITS", "OVERRIDES", "RAISES",
            "DEFINES_ROUTE", "HTTP_REQUEST",
        }
        self.assertTrue(expected_types <= kinds, expected_types - kinds)
        self.assertTrue(any(edge["status"] == "resolved" and edge["type"] == "CALLS" for edge in result["edges"]))
        self.assertTrue(expected_types - {"CONTAINS"} <= {edge["type"] for edge in result["file_edges"]})
        self.assertEqual(result["warnings"], [])
        node_ids = {node["id"] for node in result["nodes"]}
        self.assertTrue(all(edge["source"] in node_ids and edge["target"] in node_ids for edge in result["edges"]))

    def test_demo_has_concrete_examples_of_every_relationship(self):
        result = analyze_directory(str(self.demo))
        examples = {
            "CONTAINS": ("app.services.UserService", "app.services.UserService.create"),
            "IMPORTS": ("app/services.py", "app.repositories.base.UserRepository"),
            "CALLS": ("app.routes.users.create_user_route", "app.services.create_user"),
            "INSTANTIATES": ("app.services.build_user_service", "app.services.UserService"),
            "REFERENCES": ("app.events.build_event_bus", "app.events.on_user_created"),
            "USES_TYPE": ("app.services.fetch_user", "app.models.User"),
            "DECORATED_BY": ("app.services.UserService.create", "app.decorators.traced"),
            "INHERITS": ("app.repositories.memory.MemoryUserRepository", "app.repositories.base.UserRepository"),
            "OVERRIDES": ("app.repositories.memory.MemoryUserRepository.save", "app.repositories.base.UserRepository.save"),
            "RAISES": ("app.validators.validate_email", "app.errors.ValidationError"),
            "DEFINES_ROUTE": ("app.routes.users.create_user_route", "/users"),
            "HTTP_REQUEST": ("app.clients.directory.DirectoryClient.fetch", "httpx.AsyncClient.get"),
        }
        for relation, endpoints in examples.items():
            with self.subTest(relation=relation):
                self.assertIn(endpoints, self.relationships(result, relation))

    def test_demo_shows_nested_recursive_aliased_and_dynamic_calls(self):
        result = analyze_directory(str(self.demo))
        self.assertIn(("app.decorators.traced", "app.decorators.traced.wrapped"), self.relationships(result, "CONTAINS"))
        self.assertIn(("app.workflows.batch_users", "app.workflows.batch_users"), self.relationships(result, "CALLS"))
        self.assertIn(("app.jobs.run_report_alias", "app.reports.generate_report"), self.relationships(result, "CALLS"))
        self.assertIn(("app.services.build_user_service", "app.clients.directory.DirectoryClient"), self.relationships(result, "INSTANTIATES"))
        self.assertIn(("app.reports.generate_report", "app.reports.CsvReportBuilder.render"), self.relationships(result, "CALLS"))
        plugin = next(node for node in result["nodes"] if node.get("qualname") == "app.plugins.invoke_plugin")
        self.assertTrue(any(edge["source"] == plugin["id"] and edge["type"] == "CALLS" and edge["status"] == "unresolved" for edge in result["edges"]))

    def test_exclusions_and_gitignore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "venv").mkdir()
            (root / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
            (root / "src" / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
            (root / "venv" / "skip.py").write_text("def skip():\n    return 2\n", encoding="utf-8")
            (root / "ignored.py").write_text("def ignored():\n    return 3\n", encoding="utf-8")
            result = analyze_directory(directory)
            paths = {node["path"] for node in result["nodes"] if node["kind"] == "file"}
            self.assertEqual(paths, {"src/ok.py"})

    def test_syntax_error_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "good.py").write_text("def good():\n    return 1\n", encoding="utf-8")
            (root / "bad.py").write_text("def broken(:\n", encoding="utf-8")
            result = analyze_directory(directory)
            self.assertEqual(result["stats"]["files"], 1)
            self.assertTrue(any(w["code"] == "SYNTAX_ERROR" for w in result["warnings"]))

    def test_missing_directory(self):
        with self.assertRaises(ValueError):
            analyze_directory(str(self.demo / "missing"))

    def test_supported_files_only_and_binary_recovery(self):
        result = self.analyze_sources({
            "main.py": "pass",
            "app.js": "export const value = 1;",
            "image.png": "not really a picture",
            "binary.txt": "binary\x00content",
            ".env": "SECRET=value",
        })
        paths = {node["path"] for node in result["nodes"] if node["kind"] == "file"}
        self.assertEqual(paths, {"main.py", "app.js"})
        self.assertTrue(any(warning["code"] == "BINARY_FILE" for warning in result["warnings"]))

    def test_gitignore_directories_nested_names_and_negation(self):
        result = self.analyze_sources({
            ".gitignore": "generated/\nignored.py\n/root.py\n*.js\n!keep.js\n",
            "generated/deep/skip.py": "pass",
            "pkg/ignored.py": "pass",
            "root.py": "pass",
            "pkg/root.py": "pass",
            "skip.js": "const skip = 1;",
            "keep.js": "const keep = 1;",
        })
        paths = {node["path"] for node in result["nodes"] if node["kind"] == "file"}
        self.assertEqual(paths, {"pkg/root.py", "keep.js"})

    def test_source_path_traversal_is_rejected_by_path_logic(self):
        root = self.demo.resolve()
        candidate = (root / ".." / "secret.py").resolve()
        with self.assertRaises(ValueError):
            candidate.relative_to(root)

if __name__ == "__main__":
    unittest.main()
