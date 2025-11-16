import json
import math
from pathlib import Path

DEFAULT_CHARS_PER_TOKEN = 4

def estimate_tokens_from_text(text: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / chars_per_token)

def file_info(path: Path, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> dict:
    try:
        b = path.read_bytes()
        text = b.decode('utf-8', errors='replace')
        size = len(b)
        lines = text.count('\n') + (1 if text and not text.endswith('\n') else 0)
        tokens = estimate_tokens_from_text(text, chars_per_token)
    except Exception:
        size = 0
        lines = 0
        tokens = 0
    return {
        "type": "file",
        "name": path.name,
        "path": str(path),
        "size_bytes": size,
        "line_count": lines,
        "approx_tokens": tokens,
    }

def build_tree(root: Path, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> dict:
    root = Path(root).resolve()
    def _recurse(p: Path):
        if p.is_file():
            return file_info(p, chars_per_token)
        node = {
            "type": "directory",
            "name": p.name,
            "path": str(p),
            "children": [],
            "totals": {"size_bytes": 0, "approx_tokens": 0, "file_count": 0, "dir_count": 0}
        }
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except Exception:
            entries = []
        for e in entries:
            if e.name.startswith('.git'):
                continue
            child = _recurse(e)
            node["children"].append(child)
            if child.get("type") == "file":
                node["totals"]["size_bytes"] += child.get("size_bytes", 0)
                node["totals"]["approx_tokens"] += child.get("approx_tokens", 0)
                node["totals"]["file_count"] += 1
            else:
                t = child.get("totals", {})
                node["totals"]["size_bytes"] += t.get("size_bytes", 0)
                node["totals"]["approx_tokens"] += t.get("approx_tokens", 0)
                node["totals"]["file_count"] += t.get("file_count", 0)
                node["totals"]["dir_count"] += 1 + t.get("dir_count", 0)
        return node
    return _recurse(root)

def generate_file_tree_json(root_path: str, chars_per_token: int = DEFAULT_CHARS_PER_TOKEN) -> dict:
    tree = build_tree(Path(root_path), chars_per_token)
    return {"root": str(Path(root_path).resolve()), "chars_per_token": chars_per_token, "tree": tree}

# Optional: small CLI when run directly
if __name__ == "__main__":
    import argparse, sys
    p = argparse.ArgumentParser()
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--chars-per-token", type=int, default=DEFAULT_CHARS_PER_TOKEN)
    p.add_argument("-o", "--out", help="Output JSON file")
    args = p.parse_args()
    out = generate_file_tree_json(args.path, args.chars_per_token)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
    else:
        print(json.dumps(out, indent=2, ensure_ascii=False))
