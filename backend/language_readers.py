"""Language-aware file readers used by the project analyzer."""
from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

@dataclass(frozen=True)
class LanguageReader:
    name: str
    extensions: frozenset[str]
    filenames: frozenset[str] = frozenset()
    parse: Callable[[str, str], Any] | None = None

    def matches(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions or path.name in self.filenames

    def parse_source(self, source: str, filename: str) -> Any:
        return self.parse(source, filename) if self.parse else None

def _parse_python(source: str, filename: str) -> ast.AST:
    return ast.parse(source, filename=filename)

READERS = (
    LanguageReader("python", frozenset({".py", ".pyi"}), parse=_parse_python),
    LanguageReader("javascript", frozenset({".js", ".jsx", ".mjs", ".cjs"})),
    LanguageReader("typescript", frozenset({".ts", ".tsx"})),
    LanguageReader("java", frozenset({".java"})),
    LanguageReader("kotlin", frozenset({".kt", ".kts"})),
    LanguageReader("go", frozenset({".go"})),
    LanguageReader("rust", frozenset({".rs"})),
    LanguageReader("ruby", frozenset({".rb"})),
    LanguageReader("php", frozenset({".php"})),
    LanguageReader("csharp", frozenset({".cs"})),
    LanguageReader("c_cpp", frozenset({".c", ".h", ".cc", ".cpp", ".cxx", ".hpp"})),
    LanguageReader("swift", frozenset({".swift"})),
    LanguageReader("objective_c", frozenset({".m", ".mm"})),
    LanguageReader("scala", frozenset({".scala"})),
    LanguageReader("web", frozenset({".html", ".htm", ".css", ".scss", ".sass", ".less", ".vue", ".svelte", ".astro"})),
    LanguageReader("data", frozenset({".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".sql", ".graphql", ".gql"})),
    LanguageReader("text", frozenset({".md", ".mdx", ".txt", ".rst", ".csv", ".lock", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd"}), frozenset({"Dockerfile", "Containerfile", "Makefile", "justfile", "Procfile", "Gemfile", "Rakefile", "LICENSE", "README", "CHANGELOG"})),
)

def reader_for(path: Path) -> LanguageReader | None:
    return next((reader for reader in READERS if reader.matches(path)), None)

def language_for(path: Path) -> str:
    reader = reader_for(path)
    return reader.name if reader else "text"

def should_read(path: Path) -> bool:
    return reader_for(path) is not None
