import os

IGNORE = {"__pycache__", ".git", ".venv", ".idea",".pytest_cache"}

def tree(path, level=0):
    for item in os.listdir(path):
        if item in IGNORE:
            continue
        full_path = os.path.join(path, item)
        print("  " * level + "|-- " + item)
        if os.path.isdir(full_path):
            tree(full_path, level + 1)

tree(".")