# SecureBYTE_Backend

## Setup Instructions

1. **Clone the repository** and navigate to the project directory.
2. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
3. **Download your Firebase service account JSON file** from the Firebase Console and place it in the project directory.
4. **Set the environment variable** before running the app (replace the path with your actual file path):
   - **Windows PowerShell:**
     ```powershell
     $env:FIREBASE_SERVICE_ACCOUNT="C:\\path\\to\\your\\serviceAccount.json"
     python app.py
     ```
   - **Linux/macOS:**
     ```sh
     export FIREBASE_SERVICE_ACCOUNT="/path/to/your/serviceAccount.json"
     python app.py
     ```

## Environment Variables
- `FIREBASE_SERVICE_ACCOUNT`: Path to your Firebase service account JSON file. **Required.**

## API Endpoints

### Home
- `GET /`
  - Returns a welcome message.

### Create Item
- `POST /items`
  - **Body:** JSON object representing the item.
  - **Response:** `{ "id": <item_id>, "message": "Item created" }`

### Get All Items
- `GET /items`
  - **Response:** List of all items in the database.

### Update Item
- `PUT /items/<item_id>`
  - **Body:** JSON object with fields to update.
  - **Response:** `{ "message": "Item updated" }`

### Delete Item
- `DELETE /items/<item_id>`
  - **Response:** `{ "message": "Item deleted" }`

## Notes
- The backend uses Firebase Realtime Database for storage.
- CORS is enabled for all routes.
- This server is for development purposes. For production, use a production-ready WSGI server.