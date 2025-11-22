import asyncio
import os
import ast
import argparse
from openai import AsyncOpenAI, OpenAIError
from dotenv import load_dotenv

# --- Setup ---
load_dotenv()
try:
    # We use AsyncOpenAI for parallel requests
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except OpenAIError as e:
    print(f"Error initializing OpenAI client: {e}")
    print("Please check your .env file and API key.")
    exit(1)

# The "persona" for the AI
SYSTEM_PROMPT = (
    "You are 'SecureByte', a world-class AI security and code quality analyst. "
    "Your task is to analyze the following Python code chunk. "
    "Identify potential bugs, logic errors, and security vulnerabilities (like SQL injection, XSS, insecure file handling, etc.). "
    "Provide a concise, bulleted list of your findings. "
    "If there are no issues, simply state: 'No issues found in this chunk.'"
)

# --- Code Chunking Logic ---

def chunk_code_by_ast(code_string: str) -> list[str]:
    """
    Intelligently splits code by functions and classes using AST.
    """
    try:
        tree = ast.parse(code_string)
        chunks = []
        
        # Keep track of top-level code (imports, constants, etc.)
        top_level_code = []
        last_node_end = 0

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # First, save any top-level code that came before this node
                node_start_line = node.lineno - 1
                # Get the source lines for the top-level code
                if node_start_line > last_node_end:
                    top_level_chunk_lines = code_string.splitlines()[last_node_end:node_start_line]
                    top_level_chunk = "\n".join(top_level_chunk_lines).strip()
                    if top_level_chunk:
                        # Find all imports in this top-level chunk
                        import_lines = [line for line in top_level_chunk.splitlines() if line.strip().startswith(('import ', 'from '))]
                        if import_lines:
                             # If it's just imports, add them to the start of the next 'real' chunk
                             top_level_code.extend(import_lines)
                        else:
                             # It's 'real' code (constants, global vars), save it as its own chunk
                             if top_level_code:
                                 top_level_chunk = "\n".join(top_level_code) + "\n" + top_level_chunk
                                 top_level_code = [] # clear
                             chunks.append(top_level_chunk)
                
                # Now, save the function/class as its own chunk
                # Add any pending top-level imports to this chunk
                imports = "\n".join(top_level_code) + "\n" if top_level_code else ""
                
                # Get the full source code for the node
                chunk_str = ast.get_source_segment(code_string, node)
                if chunk_str:
                    chunks.append(imports + chunk_str)
                    top_level_code = [] # Imports have been used
                
                last_node_end = getattr(node, 'end_lineno', node_start_line)

            else:
                # It's not a function/class, might be top-level code
                # We'll collect it and append it at the end
                pass
        
        # Add any remaining top-level code at the end
        remaining_code = "\n".join(code_string.splitlines()[last_node_end:]).strip()
        if remaining_code:
            if top_level_code:
                 remaining_code = "\n".join(top_level_code) + "\n" + remaining_code
            chunks.append(remaining_code)

        # If AST parsing fails or returns no chunks, fall back
        if not chunks:
            raise SyntaxError("AST parsing yielded no chunks, falling back.")

        return chunks

    except (SyntaxError, ValueError):
        # Fallback for invalid Python or if ast.get_source_segment fails
        print("AST chunking failed (likely a syntax error). Falling back to simple chunker.")
        return chunk_code_by_lines(code_string, 200)

def chunk_code_by_lines(code_string: str, lines_per_chunk: int = 200) -> list[str]:
    """
    A simple fallback that splits code by line count.
    """
    lines = code_string.splitlines()
    chunks = []
    for i in range(0, len(lines), lines_per_chunk):
        chunk = "\n".join(lines[i:i + lines_per_chunk])
        chunks.append(chunk)
    return chunks

# --- Asynchronous API Call Logic ---

async def analyze_chunk(chunk_content: str, chunk_number: int) -> dict:
    """
    Sends a single code chunk to the OpenAI API for analysis.
    """
    # Get the first line for a nice console log
    first_line = chunk_content.strip().splitlines()[0]
    print(f"Analyzing chunk starting with: {first_line}...")

    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",  # You can upgrade to gpt-4-turbo for better analysis
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": chunk_content}
            ],
            temperature=0.1,
        )
        analysis = response.choices[0].message.content
        return {"chunk": chunk_number, "analysis": analysis}
    
    except OpenAIError as e:
        # Handle API errors (rate limits, connection issues)
        print(f"Error analyzing chunk: {e}")
        return {"chunk": chunk_number, "analysis": f"Error: Could not analyze chunk. {e}"}
    except Exception as e:
        # Handle other unexpected errors
        print(f"An unexpected error occurred: {e}")
        return {"chunk": chunk_number, "analysis": f"Error: An unexpected error occurred. {e}"}

# --- Main Execution ---

async def main_analysis_function(filepath: str):
    """
    Orchestrates the entire parallel analysis process.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code_to_analyze = f.read()
        print(f"--- Successfully loaded file: {filepath} ---")
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    print("--- Starting Code Chunking ---")
    chunks = chunk_code_by_ast(code_to_analyze)
    print(f"Code split into {len(chunks)} logical chunks.")

    # !!!!!!!!!!!!!!!!!!
    # NEW DIAGNOSTIC CODE
    # !!!!!!!!!!!!!!!!!!
    print("\n--- Chunking Diagnostics ---")
    total_chars = 0
    for i, chunk in enumerate(chunks):
        chunk_len = len(chunk)
        print(f"Chunk {i+1}: {chunk_len} characters")
        total_chars += chunk_len
    print(f"Total characters: {total_chars} (Original: {len(code_to_analyze)})")
    print("----------------------------\n")
    # !!!!!!!!!!!!!!!!!!
    # END OF NEW CODE
    # !!!!!!!!!!!!!!!!!!


    print("--- Starting Parallel Analysis (All chunks at once!) ---")
    # Create a list of "tasks" to run concurrently
    tasks = [analyze_chunk(chunk, i + 1) for i, chunk in enumerate(chunks)]
    
    # asyncio.gather runs all tasks in parallel and waits for all to complete
    results = await asyncio.gather(*tasks)
    print("\n--- All Analyses Complete ---")

    # Sort results back into the correct order
    results.sort(key=lambda x: x["chunk"])

    # --- Print Final Report ---
    print("\n--- SecureByte Parallel Analysis Report ---")
    for res in results:
        print(f"\n--- Analysis for Chunk {res['chunk']} ---")
        print(res['analysis'])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SecureByte Parallel Code Analyzer")
    parser.add_argument(
        "-f", 
        "--file", 
        default="test_files/test_1.py", 
        help="Path to the Python file to analyze."
    )
    args = parser.parse_args()

    # asyncio.run() is the simple way to run the main async function
    asyncio.run(main_analysis_function(args.file))

