import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from pycompare.pycompare import cli
"""
log_path = os.path.join(os.getcwd(), "nuitka_test.log")
with open(log_path, "w", encoding="utf-8") as f:
    f.write("Start\n")
"""

if __name__ == "__main__":
    try:
        cli()
    except Exception as e:
        """
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"Error: {type(e).__name__}: {e}\n")
        """
        pass
