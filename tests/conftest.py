"""Pytest configuration.

tests/fixtures/ holds small Python packages that the graph tests analyse.  They are data,
not test modules, so they are excluded from collection.
"""

collect_ignore_glob = ["fixtures/*"]
