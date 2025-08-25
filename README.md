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

## Environment Variables
- `FIREBASE_SERVICE_ACCOUNT`: Path to your Firebase service account JSON file. **Required.**
- `GITHUB_CLIENT_ID`: GitHub OAuth app client ID. **Required for token exchange endpoint.**
- `GITHUB_CLIENT_SECRET`: GitHub OAuth app client secret. **Required for token exchange endpoint.**
- `GITHUB_REDIRECT_URI`: Redirect URI used in OAuth flow. **Optional if the frontend sends it in the request.**

## Database Schema

The application uses Firebase Realtime Database with the following structure:

```
users/
  {user_id}/
    projects/
      {project_id}/
        - projectid (UUID)
        - project_name (string, required)
        - project_desc (string, optional)
        - fileids (array of submission UUIDs)
        - securityrev (array of strings - optional, AI review history)
        - logicrev (array of strings - optional, AI review history)
        - testingrev (array of strings - optional, AI review history)
        - created_at (ISO timestamp)
        - updated_at (ISO timestamp)
    submissions/
      {submission_id}/
        - id (UUID)
        - projectid (UUID reference to parent project)
        - filename (string, required)
        - code (string, optional)
        - securityrev (array of strings - LLM security review output)
        - logicrev (array of strings - LLM logic review output)
        - testcases (array of strings - LLM test cases output)
        - reviewpdf (string - path/identifier for LaTeX-generated PDF)
        - created_at (ISO timestamp)
        - updated_at (ISO timestamp)
```

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

## Data Features

- **User Isolation:** All data is scoped to individual users via `user_id`
- **UUID Generation:** Projects and submissions automatically receive unique UUIDs
- **Automatic Timestamps:** `created_at` and `updated_at` fields are managed automatically
- **Referential Integrity:** Projects maintain references to their submissions via `fileids` array
- **Cascading Deletes:** Deleting a project removes all associated submissions
- **Array Support:** Supports arrays for LLM outputs (security reviews, logic reviews, test cases)

## Error Handling

- **400 Bad Request:** Missing required fields
- **404 Not Found:** Resource doesn't exist
- **201 Created:** Successful resource creation
- **200 OK:** Successful operation

## Notes
- The backend uses Firebase Realtime Database for storage.
- CORS is enabled for all routes.