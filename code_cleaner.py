import re
import sys
from pathlib import Path

def compress_code(code: str) -> str:
    # Remove triple-quoted strings (docstrings)
    code = re.sub(r'(""".*?"""|\'\'\'.*?\'\'\')', '', code, flags=re.DOTALL)
    # Remove single-line comments
    code = re.sub(r'#.*', '', code)
    # Remove imports
    code = re.sub(r'^\s*import .*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*from .* import .*$', '', code, flags=re.MULTILINE)
    # Remove blank lines
    code = "\n".join(line for line in code.splitlines() if line.strip())
    # Collapse into one line
    code = "".join(code.splitlines())
    # Remove ALL spaces
    code = code.replace(" ", "")
    return code

def compress_folder(input_folder: Path, output_folder: Path):
    for py_file in input_folder.rglob("*.py"):  # Recursively find all .py files
        rel_path = py_file.relative_to(input_folder)
        out_file = output_folder / rel_path
        out_file.parent.mkdir(parents=True, exist_ok=True)

        with open(py_file, "r", encoding="utf-8") as f:
            code = f.read()

        compressed = compress_code(code)

        with open(out_file, "w", encoding="utf-8") as f:
            f.write(compressed)

        print(f"Compressed {py_file} -> {out_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compress.py <folder> [output_folder]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path / "cleaned"

    compress_folder(input_path, output_path)
