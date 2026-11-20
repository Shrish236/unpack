"""Unpack code knowledge graph: a tree-sitter based builder for Python repositories.

Pass 1 (`extract`) parses each file independently into a `ModuleInfo`.  Later passes add
call resolution, test reachability, change detection and Neo4j output.
"""

from .extract import extract_file, module_name_for, package_predicates
from .model import FuncInfo, ModuleInfo, Shape
from .source import FsSource, GitSource

__all__ = [
    "FsSource",
    "GitSource",
    "FuncInfo",
    "ModuleInfo",
    "Shape",
    "extract_file",
    "module_name_for",
    "package_predicates",
]
