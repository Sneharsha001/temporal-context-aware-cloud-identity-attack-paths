import sys
import os

workspace_root = os.path.dirname(os.path.dirname(__file__))
tests_dir = os.path.dirname(__file__)

def pytest_sessionstart(session):
    """Called after the Session object has been created and before performing collection."""
    # Remove tests directory from sys.path if present (pytest adds it during collection)
    if tests_dir in sys.path:
        sys.path.remove(tests_dir)
    # Insert workspace root at the very beginning
    if workspace_root not in sys.path:
        sys.path.insert(0, workspace_root)

# Also run at module level for good measure
if tests_dir in sys.path:
    sys.path.remove(tests_dir)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)
