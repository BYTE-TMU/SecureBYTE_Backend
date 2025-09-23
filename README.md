# SecureBYTE_Backend

## Setup Instructions

1. **Clone the repository** and navigate to the project directory.
2. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
3. **Add your Firebase service account JSON file:**
   - Download your Firebase service account JSON from the Firebase Console.
   - Place it in the project directory and rename it to `firebase.json` (or use your preferred name, but update the path accordingly).
4. **Set the environment variable** before running the app (replace the path with your actual file path):
   - **Windows PowerShell:**
     ```powershell
     $env:FIREBASE_SERVICE_ACCOUNT="C:\\path\\to\\your\\firebase.json"
     python app.py
     ```
   - **Linux/macOS:**
     ```sh
     export FIREBASE_SERVICE_ACCOUNT="/path/to/your/firebase.json"
     python app.py
     ```
   - Or, if your `firebase.json` is in the project root, you can use:
     ```sh
     export FIREBASE_SERVICE_ACCOUNT="$(pwd)/firebase.json"
     python app.py
     ```

  - Alternatively, create a `.env` file in `SecureBYTE_Backend/` with:
    ```env
    FIREBASE_SERVICE_ACCOUNT=/absolute/path/to/firebase.json
    GITHUB_CLIENT_ID=your_client_id
    GITHUB_CLIENT_SECRET=your_client_secret
    GITHUB_REDIRECT_URI=https://yourapp.example.com/callback
    ```
    The app will automatically load this file at startup.

## Environment Variables
- `FIREBASE_SERVICE_ACCOUNT`: Path to your Firebase service account JSON file. **Required.**
- `GITHUB_CLIENT_ID`: GitHub OAuth app client ID. **Required for token exchange endpoint.**
- `GITHUB_CLIENT_SECRET`: GitHub OAuth app client secret. **Required for token exchange endpoint.**
- `GITHUB_REDIRECT_URI`: Redirect URI used in OAuth flow. **Optional if the frontend sends it in the request.**

You can set these in your shell as shown above, or place them in a `.env` file in `SecureBYTE_Backend/`.

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
- The following submission fields are deprecated and ignored on create and update: `securityrev`, `reviewpdf`.
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

#### Get All Projects for User
- `GET /users/{user_id}/projects`
  - **Response:** Array of project objects

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

#### Save Project Files
- `PUT /users/{user_id}/projects/{project_id}/save`
  - **Description:** Atomically save multiple edited files within a project. If any file fails validation, no updates are applied.
  - **Body (array of files):**
    ```json
    [
      {
        "fileid": "<submission uuid>",
        "filename": "relative/path/to/file.ext",
        "code": "<updated file contents>"
      }
    ]
    ```
  - **Success Response:** `{ "message": "Project saved successfully" }`
  - **Failure (400):**
    ```json
    {
      "error": "Not all files could be saved",
      "failed_files": [ { "fileid": "...", "filename": "...", "error": "..." } ],
      "total_failed": 1,
      "total_files": 3
    }
    ```

### Submissions

#### Create Submission
- `POST /users/{user_id}/projects/{project_id}/submissions`
  - **Body:**
    ```json
    {
      "filename": "string (required)",
      "code": "string (optional)",
      "testcases": ["array of strings (optional)"]
    }
    ```
  - **Response:** `{ "id": "<uuid>", "message": "Submission created successfully" }`
  - **Notes:** Deprecated fields `securityrev` and `reviewpdf` are ignored.

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

## Error Handling

- **400 Bad Request:** Missing required fields
- **404 Not Found:** Resource doesn't exist
- **201 Created:** Successful resource creation
- **200 OK:** Successful operation

## Notes
- The backend uses Firebase Realtime Database for storage.
- CORS is enabled for all routes.
- Review endpoints are rate-limited to 1 request per 5 seconds. Global limits apply (200/day, 50/hour).
- LLM provider keys are read by `SecureBYTE_AI/config.py` from environment variables; see `SecureBYTE_AI/README.md` for configuration.