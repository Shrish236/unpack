"""Basic sanity tests for repository initialization and imports."""

import pathlib
import unittest

from unpack_graph.model import FuncInfo, ModuleInfo, Shape
from unpack_graph.source import FsSource


class TestBasicSetup(unittest.TestCase):
    def test_models_initialization(self):
        s = Shape(kind="name", base="test_func")
        self.assertEqual(s.kind, "name")
        self.assertEqual(s.base, "test_func")

    def test_fssource_list(self):
        root = pathlib.Path(__file__).parent.parent
        src = FsSource(root)
        files = src.list_files()
        self.assertTrue(any("unpack_graph/model.py" in f for f in files))


if __name__ == "__main__":
    unittest.main()
