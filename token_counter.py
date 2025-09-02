import tiktoken
import sys

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Return the number of tokens for the given text and model."""
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python token_counter.py <filename.py>")
        sys.exit(1)

    filename = sys.argv[1]
    with open(filename, "r", encoding="utf-8") as f:
        code = f.read()

    models = ["gpt-4", "gpt-3.5-turbo", "gpt-4o-mini"]
    for model in models:
        print(f"{model}: {count_tokens(code, model)} tokens")
