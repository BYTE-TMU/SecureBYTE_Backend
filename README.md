# SecureBYTE_Backend

## Beginner-Friendly Setup Guide

This backend is a Python Flask REST API that stores data in Firebase Realtime Database and integrates with LLMs for code reviews.

- If you’re new to Flask, skim the official tutorial to understand routes, requests, and responses: [Flask quickstart](https://flask.palletsprojects.com/).
- A minimal Flask app looks like this:
```python
from flask import Flask
app = Flask(__name__)

@app.get("/")
def home():
    return "Hello from Flask!"
```

### Prerequisites
- Python 3.10+ and `pip`
- Git
- A Firebase project with a Service Account JSON
- Optional: Postman, curl

### 1) Clone and enter the backend folder
```sh
git clone <your-monorepo-url>
cd SecureBYTE_Backend
```

### 2) Create and activate a virtual environment
- macOS/Linux:
```sh
python3 -m venv .venv
source .venv/bin/activate
```
- Windows (PowerShell):
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3) Install dependencies
```sh
pip install -r requirements.txt
```

### 4) Provide Firebase credentials
Download your Firebase service account JSON, place it anywhere, and point the app to it via an environment variable.
- macOS/Linux:
```sh
export FIREBASE_SERVICE_ACCOUNT="/absolute/path/to/firebase.json"
```
- Windows (PowerShell):
```powershell
$env:FIREBASE_SERVICE_ACCOUNT="C:\absolute\path\to\firebase.json"
```
Tip: If `firebase.json` is in this folder:
```sh
export FIREBASE_SERVICE_ACCOUNT="$(pwd)/firebase.json"
```

### 5) Optional: Configure a `.env` file
Some features (e.g., GitHub OAuth, LLMs via `SecureBYTE_AI`) rely on environment variables. You can create a `.env` file in `SecureBYTE_Backend/` to load values at startup:
```env
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_REDIRECT_URI=http://localhost:5173/auth/callback
# LLM provider keys are read by SecureBYTE_AI/config.py (see that README)
```
See the Environment Variables section below for details.

### 6) Run the server
```sh
python app.py
```
The app will start on `http://127.0.0.1:5000`. Test the health route:
```sh
curl http://127.0.0.1:5000/
```

### 7) Quickstart calls
- Create a project:
```sh
curl -X POST http://127.0.0.1:5000/users/demo-user/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name":"my-first-project","project_desc":"hello"}'
```
- Create a submission:
```sh
curl -X POST http://127.0.0.1:5000/users/demo-user/projects/<project_id>/submissions \
  -H "Content-Type: application/json" \
  -d '{"filename":"main.py","code":"print(42)"}'
```

### 8) Run tests (optional)
Install pytest (dev only) and run:
```sh
pip install pytest
pytest -q
```

### 9) Postman collection (optional)
Import `postman/SecureBYTE_Review_Endpoints.postman_collection.json` into Postman to try the review endpoints.

### Troubleshooting
- If the app exits with “FIREBASE_SERVICE_ACCOUNT environment variable not set.”, ensure the env var points to your JSON and that the path is absolute.
- Review endpoints require LLM keys configured in `SecureBYTE_AI`; without them you’ll see “LLM not available on server”.

## Contributor Guide: How SecureBYTE Backend Works

### Architecture at a glance
- `app.py`: Single-file Flask app with all routes.
- Storage: Firebase Realtime Database via `firebase_admin.db.reference`.
- LLM integration: `SecureBYTE_AI.main.LLMManager`, prompts in `prompts/`.
- Rate limiting: `Flask-Limiter` with global and per-route limits.
- CORS: Enabled for all routes.
- GitHub integration: OAuth token exchange, repo listing, project linking, and repo import.

### Request flow for reviews
1. Client calls a review endpoint.
2. Handler validates/normalizes input and fetches the latest code from Firebase.
3. `handle_llm_review()` loads the correct prompt, compresses code (`code_cleaner.compress_code`), and calls `llm.generate_response(...)`.
4. The JSON response is stored:
   - Project-level: `projects.{project_id}.securityrev`
   - Submission-level: `submissions.{submission_id}.logicrev` or `testingrev`

### Data model highlights
- Project keeps an array of submission IDs in `fileids`.
- Project-level `securityrev`; submission-level `logicrev` and `testingrev`.
- Filenames are normalized to safe, POSIX-style relative paths.
- Deprecated on submissions: `securityrev`, `reviewpdf` (ignored on update).

### Rate limits
- Global: 200/day, 50/hour.
- Per review endpoint: 1 request per 5 seconds per client.

### GitHub integration overview
- `POST /auth/github/exchange-token`: swap code → access token.
- `GET /users/{user_id}/github/repos`: list repos (requires `Authorization: Bearer <token>`).
- `POST /users/{user_id}/projects/{project_id}/github/link`: store repo+branch on a project.
- `POST /users/{user_id}/projects/{project_id}/github/import`: import repo files as submissions.

### Adding a new endpoint (recipe)
```python
from firebase_admin import db
from flask import request, jsonify

@app.route('/users/<user_id>/examples', methods=['POST'])
def create_example(user_id):
    data = request.get_json(silent=True) or {}
    if 'name' not in data:
        return jsonify({'error': 'name is required'}), 400
    ref = db.reference(f'users/{user_id}/examples')
    ref.update({'last_created': get_timestamp(), 'name': data['name']})
    return jsonify({'message': 'Example created'})
```
Guidelines:
- Validate input early; return clear 400 errors.
- Use `db.reference` with user-scoped paths.
- Update `updated_at` timestamps when mutating resources.
- Keep filenames relative and normalized (see `normalize_relative_path`).

### Testing
- Unit tests use pytest and mock Firebase/LLM to avoid external calls.
- See `tests/test_logic_and_testing_reviews.py` and `tests/test_security_review.py` for fixtures/mocks and happy-path tests.
- For quick manual testing, run `tests/manual_test_save_project.py` (uses live server via HTTP).

### Contributing
- Create a feature branch, make changes with clear commits, add/update tests when relevant, and open a pull request.
- Keep code readable and follow existing patterns: early returns for errors, consistent JSON responses, and minimal side effects in handlers.

## Environment Variables
- `FIREBASE_SERVICE_ACCOUNT`: Path to your Firebase service account JSON file. **Required.**
- `GITHUB_CLIENT_ID`: GitHub OAuth app client ID. **Required for token exchange endpoint.**
- `GITHUB_CLIENT_SECRET`: GitHub OAuth app client secret. **Required for token exchange endpoint.**
- `GITHUB_REDIRECT_URI`: Redirect URI used in OAuth flow. **Optional if the frontend sends it in the request.**

## Database Schema

The application uses Firebase Realtime Database with the following structure (current, authoritative):

```
users/
  {user_id}/
    projects/
      {project_id}/
        - projectid (UUID)
        - project_name (string, required)
        - project_desc (string, optional)
        - fileids (array of submission UUIDs)
        - securityrev (array of objects - project-level security review history)
        - github (object, optional: { repo_full_name, branch, linked_at })
        - created_at (ISO timestamp)
        - updated_at (ISO timestamp)
    submissions/
      {submission_id}/
        - id (UUID)
        - projectid (UUID reference to parent project)
        - filename (string, required; normalized relative path)
        - code (string)
        - logicrev (array of objects - LLM logic review history)
        - testingrev (array of objects - LLM testing review history)
        - testcases (array of strings - optional)
        - created_at (ISO timestamp)
        - updated_at (ISO timestamp)
```

Notes and deprecations:
- Security reviews are stored on the project (`projects.{project_id}.securityrev`).
- The following submission fields are deprecated and ignored on update: `securityrev`, `reviewpdf`.
- Filenames are stored as normalized, POSIX-style relative paths (no absolute paths or `..`).

## API Endpoints

### Home
- `GET /`
  - Returns a welcome message.

### Projects

#### Create Project
- `POST /users/{user_id}/projects`
  - **Body:** 
    ```json
    {
      "project_name": "string (required)",
      "project_desc": "string (optional)"
    }
    ```
  - **Response:** `{ "projectid": "<uuid>", "message": "Project created successfully" }`

#### Get All Projects for User (with Sorting)
- `GET /users/{user_id}/projects`
  - **Query Parameters:**
    - `sort_by` (optional): Field to sort by. Valid options: `project_name`, `created_at`, `updated_at` (default: `updated_at`)
    - `order` (optional): Sort order. Valid options: `asc`, `desc` (default: `desc`)
  - **Examples:**
    ```
    GET /users/u123/projects                                    # Default: sort by updated_at desc
    GET /users/u123/projects?sort_by=project_name&order=asc    # Sort by name A-Z
    GET /users/u123/projects?sort_by=project_name&order=desc   # Sort by name Z-A
    GET /users/u123/projects?sort_by=created_at&order=asc      # Sort by creation date (oldest first)
    GET /users/u123/projects?sort_by=created_at&order=desc     # Sort by creation date (newest first)
    GET /users/u123/projects?sort_by=updated_at&order=desc     # Sort by last updated (newest first)
    ```
  - **Response:**
    ```json
    {
      "projects": [
        {
          "projectid": "<uuid>",
          "project_name": "Project Name",
          "project_desc": "Description",
          "fileids": [],
          "created_at": "2025-01-01T00:00:00",
          "updated_at": "2025-01-02T00:00:00"
        }
      ],
      "sort_by": "project_name",
      "order": "asc",
      "total": 1
    }
    ```
  - **Notes:**
    - Project name sorting is case-insensitive
    - Invalid `sort_by` or `order` values return 400 Bad Request
    - Empty project lists are handled gracefully

#### Get Specific Project
- `GET /users/{user_id}/projects/{project_id}`
  - **Response:** Project object or 404 if not found

#### Update Project
- `PUT /users/{user_id}/projects/{project_id}`
  - **Body:** JSON object with fields to update
  - **Response:** `{ "message": "Project updated successfully" }`

#### Delete Project
- `DELETE /users/{user_id}/projects/{project_id}`
  - **Response:** `{ "message": "Project and related submissions deleted successfully" }`
  - **Note:** This also deletes all submissions associated with the project

#### Delete Multiple Projects (Batch)
- `DELETE /users/{user_id}/projects_delete`
  - **Body:**
    ```json
    {
      "ids": ["<project_id_1>", "<project_id_2>"]
    }
    ```
  - **Response:** `{ "message": "Deleted N project(s) and related submissions successfully" }`
  - **Notes:**
    - If `ids` is missing or empty, the server returns **400 Bad Request**.
    - If none of the provided IDs match existing projects, the server returns **404 Not Found** and does not delete anything.

### Submissions

#### Create Submission
- `POST /users/{user_id}/projects/{project_id}/submissions`
  - **Body:**
    ```json
    {
      "filename": "string (required)",
      "code": "string (optional)",
      "securityrev": ["array of strings (optional)"],
      "logicrev": ["array of strings (optional)"],
      "testcases": ["array of strings (optional)"],
      "reviewpdf": "string (optional)"
    }
    ```
  - **Response:** `{ "id": "<uuid>", "message": "Submission created successfully" }`

#### Get All Submissions for Project
- `GET /users/{user_id}/projects/{project_id}/submissions`
  - **Response:** Array of submission objects for the specified project

#### Get Specific Submission
- `GET /users/{user_id}/submissions/{submission_id}`
  - **Response:** Submission object or 404 if not found

#### Update Submission
- `PUT /users/{user_id}/submissions/{submission_id}`
  - **Body:** JSON object with fields to update
  - **Response:** `{ "message": "Submission updated successfully" }`

#### Delete Submission
- `DELETE /users/{user_id}/submissions/{submission_id}`
  - **Response:** `{ "message": "Submission deleted successfully" }`
  - **Note:** This also removes the submission ID from the parent project's fileids array

#### Get Submission Code Only
- `GET /users/{user_id}/submissions/{submission_id}/code`
  - **Response:** `{ "code": "<string>" }`

#### Local Folder Upload (Batch JSON)
- `POST /users/{user_id}/projects/{project_id}/submissions/batch`
  - **Description:** Upload many files at once by sending their relative paths and contents as JSON. This preserves folder structure via the `filename` field used by the frontend file tree.
  - **Body:**
    ```json
    {
      "files": [
        { "path": "src/index.js", "content": "console.log('hi')" },
        { "path": "src/components/App.jsx", "content": "export default function App(){}" }
      ],
      "max_files": 1000,
      "max_bytes": 5242880
    }
    ```
  - **Response:**
    ```json
    {
      "message": "Batch upload complete",
      "created": 2,
      "created_ids": ["<uuid>", "<uuid>"]
    }
    ```
  - **Notes:**
    - `path` must be a relative path (no leading `/`, no `..`). Invalid paths are skipped.
    - `max_files` and `max_bytes` are optional caps; files exceeding `max_bytes` are skipped.

#### Local Folder Upload (Multipart)
- `POST /users/{user_id}/projects/{project_id}/submissions/upload`
  - **Description:** Upload many files using `multipart/form-data`. Optionally provide an array of relative paths aligned to the uploaded files. If no path is provided for a file, its filename is used.
  - **Form fields:**
    - `files`: multiple file parts (name="files")
    - `relative_paths`: JSON array of strings aligned to `files` order (optional)
    - `max_files`: integer (optional)
    - `max_bytes`: integer (optional, per-file cap)
  - **Example (pseudo):**
    ```
    FormData:
      files: <File src/index.js>
      files: <File src/components/App.jsx>
      relative_paths: ["src/index.js", "src/components/App.jsx"]
      max_files: 1000
      max_bytes: 5242880
    ```
  - **Response:**
    ```json
    {
      "message": "Upload complete",
      "created": 2,
      "created_ids": ["<uuid>", "<uuid>"]
    }
    ```
  - **Notes:**
    - Paths are normalized and must be relative (no `..` or absolute paths).
    - On Chromium-based browsers, the frontend can use `input[webkitdirectory]` and `file.webkitRelativePath` to populate `relative_paths` or batch JSON `path` fields.

### LLM Review Endpoints

All review endpoints are rate-limited to 1 request per 5 seconds per client. See Rate Limits below.

- `POST /users/{user_id}/submissions/{submission_id}/logic-review`
  - Updates the submission (e.g., with latest `code`) and appends a logic review to `submissions.{submission_id}.logicrev`.
  - **Body (example):** `{ "code": "<latest code>" }`
  - **Response:** `{ success, review_type: "logic", response: <JSON object> }`

- `POST /users/{user_id}/submissions/{submission_id}/testing-review`
  - Updates the submission (e.g., with latest `code`) and appends a testing review to `submissions.{submission_id}.testingrev`.
  - **Body (example):** `{ "code": "<latest code>" }`
  - **Response:** `{ success, review_type: "testing", response: <JSON object> }`

- `POST /users/{user_id}/projects/{project_id}/security-review`
  - Aggregates all files in the project (from `fileids`) and appends a security review to `projects.{project_id}.securityrev`.
  - **Body:** none required
  - **Response:** `{ success, review_type: "security", response: <JSON object> }`

### GitHub Integration

- `POST /auth/github/exchange-token`
  - Exchange OAuth code for an access token. Requires `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and optional `GITHUB_REDIRECT_URI`.

- `GET /users/{user_id}/github/repos`
  - List the authenticated user's repos (supports `per_page` and `page`). Requires `Authorization: Bearer <token>`.

- `POST /users/{user_id}/projects/{project_id}/github/link`
  - Link a project to a GitHub repo and branch.
  - **Body:** `{ "repo_full_name": "owner/name", "branch": "main" }`
  - Stores `{ repo_full_name, branch, linked_at }` under `projects.{project_id}.github`.

- `POST /users/{user_id}/projects/{project_id}/github/import`
  - Imports repository files as submissions. Accepts optional `max_files`, `max_bytes`, and `branch`.
  - Creates submissions for all files (no extension filter) and updates `fileids`.

### History

- `GET /users/{user_id}/history`
  - Returns a reverse-chronological list of project and submission events for the user.

- `GET /users/{user_id}/projects/{project_id}/history`
  - Returns project-specific history including submission events.

### Metrics

- `GET /users/{user_id}/metrics`
  - Aggregated counts across projects and submissions, severity distribution from security reviews, and recent activity.

- `GET /users/{user_id}/projects/{project_id}/metrics`
  - Metrics scoped to a single project.

### Dashboard

- `GET /users/{user_id}/dashboard`
  - Quick stats, recent activity, recent projects, and recent submissions.

- `GET /users/{user_id}/dashboard/summary`
  - Summary counts and top critical issues across security reviews.

## Data Features

- **User Isolation:** All data is scoped to individual users via `user_id`.
- **UUID Generation:** Projects and submissions automatically receive unique UUIDs.
- **Automatic Timestamps:** `created_at` and `updated_at` fields are managed automatically.
- **Referential Integrity:** Projects maintain references to their submissions via `fileids` array.
- **Cascading Deletes:** Deleting a project removes all associated submissions.
- **Review Storage:** Project-level `securityrev`; submission-level `logicrev` and `testingrev`.
- **Array Support:** Arrays of review objects and optional `testcases` arrays.
- **GitHub Linking:** Projects can be linked to repos; imports create submissions and update `fileids`.
- **Path Normalization:** Uploaded/imported filenames are normalized to safe, relative paths.
- **Project Sorting:** Projects can be sorted by name, creation date, or last updated date in ascending or descending order.

## Error Handling

- **400 Bad Request:** Missing required fields or invalid parameters
- **404 Not Found:** Resource doesn't exist
- **201 Created:** Successful resource creation
- **200 OK:** Successful operation

## Notes
- The backend uses Firebase Realtime Database for storage.
- CORS is enabled for all routes.
- Review endpoints are rate-limited to 1 request per 5 seconds. Global limits apply (200/day, 50/hour).
- LLM provider keys are read by `SecureBYTE_AI/config.py` from environment variables; see `SecureBYTE_AI/README.md` for configuration.

## Technical Resources

Backend Development Learning Resource Guide — Prepared for BYTE TMU Contributor Team. These resources are free and organized from beginner to advanced.

### Beginner Level

**Recommended YouTube Courses**
- [Back-End Development Full Course – Node.js, Express & MongoDB](https://www.youtube.com/watch?v=Oe421EPjeBE)
- [Node.js Full Course 2024 | Complete Backend Development](https://www.youtube.com/watch?v=MIJt9H69QVc&utm_source=chatgpt.com)
- [Python Backend Development Crash Course](https://www.youtube.com/watch?v=PtQiiknWUcI)
- [Back-End Web Development (Tutorial for Beginners)](https://www.youtube.com/watch?v=1oTuMPIwHmk&utm_source=chatgpt.com)
- [FreeCodeCamp: APIs & Microservices](https://www.youtube.com/watch?v=GZvSYJDk-us)

**Reference Websites**
- FreeCodeCamp Backend Curriculum
- MDN Web Docs – Server-side Development

### Intermediate Level

**Recommended YouTube Courses**
- [Backend Developer Roadmap 2023](https://www.youtube.com/watch?v=CWAi_2oLhYg&utm_source=chatgpt.com)
- [Learn Python Backend by Building 3 Projects](https://www.youtube.com/watch?v=ftKiHCDVwfA&utm_source=chatgpt.com)
- [REST API Tutorial – Python & Flask](https://www.youtube.com/watch?v=GMppyAPbLYk)
- [Spring Boot Crash Course](https://www.youtube.com/watch?v=vtPkZShrvXQ)
- [Build and Deploy a REST API (Node.js + Express + MongoDB)](https://www.youtube.com/watch?v=rOpEN1JDaD0&utm_source=chatgpt.com)

**Reference Websites**
- GeeksforGeeks – Backend Development Tutorials
- DigitalOcean Tutorials

### Advanced / Expert Level

**Recommended YouTube Courses**
- [System Design Basics – FreeCodeCamp](https://www.youtube.com/watch?v=MbjObHmDbZo)
- [System Design Concepts & Interview Preparation](https://www.youtube.com/watch?v=F2FmTdLtb_4&utm_source=chatgpt.com)
- [Advanced Backend Development Roadmap 2025](https://www.youtube.com/watch?v=CxmCUpGjIvo&utm_source=chatgpt.com)
- [End-to-End Complete Advanced Backend Development (Algocamp)](https://www.youtube.com/watch?v=x4Kl3r3m8zw&utm_source=chatgpt.com)
- [How Databases Work – FreeCodeCamp](https://www.youtube.com/watch?v=HXV3zeQKqGY)
- [Event-Driven Microservices with Kafka](https://www.youtube.com/watch?v=R873BlNVUB4)

**Reference Websites**
- High Scalability Blog
- Martin Fowler’s Blog
- MDN Performance & Security Guides

### Notes for Contributors

- Begin with Beginner Level resources if you are new to backend development.
- Progress to Intermediate once you are comfortable building and deploying basic APIs.
- Move to Advanced resources for topics such as scalability, system design, and distributed architectures.
- Contributors are encouraged to document what they learn and share insights with the team.