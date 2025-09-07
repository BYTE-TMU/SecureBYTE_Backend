import os
import json
import time
import uuid
import requests


def main():
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000")
    user_id = os.getenv("USER_ID", f"tester-{uuid.uuid4()}")

    print(f"Using BASE_URL={base_url}")
    print(f"Using USER_ID={user_id}")

    # 1) Create a project
    resp = requests.post(
        f"{base_url}/users/{user_id}/projects",
        json={"project_name": "sec-review-demo", "project_desc": "automated test"},
        timeout=30,
    )
    resp.raise_for_status()
    project_id = resp.json()["projectid"]
    print(f"Created project: {project_id}")

    # 2) Create a submission under the project
    code_snippet = '''
import pandas as pd

def find_duplicate_names(csv_files, name_column="Name"):
    """
    Takes a list of CSV files and returns a list of duplicate names.
    
    Parameters:
        csv_files (list): List of file paths to CSV files
        name_column (str): Column name where names are stored (default: "Name")
        
    Returns:
        list: Duplicate names across all CSV files
    """
    all_names = []

    # Read each CSV file and collect names
    for file in csv_files:
        df = pd.read_csv(file)
        if name_column in df.columns:
            all_names.extend(df[name_column].dropna().tolist())
        else:
            print(f"Warning: {file} does not contain column '{name_column}'")

    # Find duplicates
    duplicates = set([name for name in all_names if all_names.count(name) > 1])

    return list(duplicates)


# Example usage:
csv_files = ["file1.csv", "file2.csv", "file3.csv"]  # Sample file names
duplicate_names = find_duplicate_names(csv_files, name_column="Name")
print("Duplicate Names:", duplicate_names)
'''.strip()

    resp = requests.post(
        f"{base_url}/users/{user_id}/projects/{project_id}/submissions",
        json={"filename": "insecure.py", "code": code_snippet},
        timeout=30,
    )
    resp.raise_for_status()
    submission_id = resp.json()["id"]
    print(f"Created submission: {submission_id}")

    # 3) Trigger security review
    # Endpoint collects all project fileids and sends to LLM
    print("Requesting security review...")
    resp = requests.post(
        f"{base_url}/users/{user_id}/projects/{project_id}/security-review",
        json={},
        timeout=60,
    )

    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2))
    except json.JSONDecodeError:
        print("Response was not valid JSON:")
        print(resp.text)


if __name__ == "__main__":
    main()


