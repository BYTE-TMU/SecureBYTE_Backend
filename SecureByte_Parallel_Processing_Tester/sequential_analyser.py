import asyncio
import os
import argparse  # To read command-line arguments
from dotenv import load_dotenv  # To load .env file
from openai import AsyncOpenAI

# Load environment variables from .env file
load_dotenv()

async def analyze_sequentially(client: AsyncOpenAI, full_code: str, system_prompt: str) -> str:
    """
    Sends the ENTIRE code file to the OpenAI API in a single call.
    """
    print(f"Analyzing entire file ({len(full_code)} chars) in one single call...")
    try:
        response = await client.chat.completions.create(
            model="gpt-4", # Or your preferred model
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this entire code file:\n\n```python\n{full_code}\n```"}
            ]
        )
        print("...Full file analysis complete.")
        return response.choices[0].message.content
    except Exception as e:
        # This is very likely to fail if the file is too big (TokenLimitError)
        print(f"Error analyzing full file: {e}")
        return f"Error: Could not analyze file. {e}"

async def main():
    """
    Main function to run the sequential (single-call) processing.
    """
    # Setup command-line argument parser
    parser = argparse.ArgumentParser(
        description="Analyze a Python file in ONE sequential call using OpenAI."
    )
    parser.add_argument(
        "-f", "--file",
        type=str,
        default="test_files/test_1.py", # NEW: Set the default file
        help="The path to the Python file to analyze. Defaults to test_files/test_1.py"
    )
    args = parser.parse_args()
    
    # Use the file argument
    filepath_to_analyze = args.file
    
    # Read the code from the specified file
    try:
        with open(filepath_to_analyze, 'r', encoding='utf-8') as f:
            code_to_analyze = f.read()
        print(f"--- Successfully loaded file: {filepath_to_analyze} ---")
    except FileNotFoundError:
        print(f"Error: File not found at path: {filepath_to_analyze}")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Make sure your OPENAI_API_KEY is set
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set or found in .env file.")
        return

    try:
        client = AsyncOpenAI(api_key=api_key)
    except Exception as e:
        print(f"Error initializing OpenAI client: {e}")
        return

    # System prompt
    system_prompt = (
        "You are 'SecureByte', a world-class AI security and code quality analyst. "
        "Analyze the following Python code snippet. "
        "Identify any potential logic errors, security vulnerabilities, or bugs. "
        "Provide a concise summary of your findings for this snippet."
    )

    print("\n--- Starting Sequential Analysis (One Big Call) ---")
    
    # Run the single analysis task
    result = await analyze_sequentially(client, code_to_analyze, system_prompt)
    
    print("\n--- Sequential Analysis Complete ---")

    # Print the final report
    final_report = "--- SecureByte Sequential Analysis Report ---\n\n"
    final_report += result
    final_report += "\n\n"

    print(final_report)

if __name__ == "__main__":
    asyncio.run(main())

