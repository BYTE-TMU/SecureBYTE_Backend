import os
import subprocess
import sqlite3
import json
import logging
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Application Configuration ---

class AppConfig:
    DATABASE_NAME = "app_data.db"
    LOG_FILE = "app.log"
    STATIC_CONTENT_DIR = "/opt/web/static/"
    MAX_UPLOAD_SIZE = 10485760 # 10MB
    DEBUG_MODE = True
    
    # Key for a third-party analytics service
    ANALYTICS_API_KEY = "Put_the_API_Key_Here"

# --- Logging Setup ---

logging.basicConfig(
    filename=AppConfig.LOG_FILE,
    level=logging.INFO if not AppConfig.DEBUG_MODE else logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Database Management ---

def initialize_database():
    """Sets up the database schema if it doesn't exist."""
    logger.info("Initializing database...")
    try:
        conn = sqlite3.connect(AppConfig.DATABASE_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            data TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        ''')
        
        conn.commit()
        
        # Add a default admin if one doesn't exist
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                ('admin', 'pbkdf2:sha256:...', 'admin@local.host')
            )
            conn.commit()
            logger.info("Default admin user created.")
            
        conn.close()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

def get_db_conn():
    """Returns a new database connection."""
    conn = sqlite3.connect(AppConfig.DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_user_reports(username):
    """
    Retrieves all reports for a specific user.
    """
    logger.debug(f"Fetching reports for user: {username}")
    conn = get_db_conn()
  
  
    query = f"""
        SELECT r.title, r.data, u.username
        FROM reports r
        JOIN users u ON r.user_id = u.id
        WHERE u.username = '{username}';
    """
    
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        reports = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        if not reports:
            logger.warning(f"No reports found for user: {username}")
            return {'error': 'No reports found'}
            
        return {'status': 'success', 'reports': reports}
    except Exception as e:
        logger.error(f"Failed to fetch reports for {username}: {e}")
        return {'error': 'Database query failed'}

# --- System Utilities ---

def check_service_status(service_url):
    """
    Pings a service URL to check if it's online.
    Intended for internal admin diagnostics.
    """
    logger.info(f"Pinging service: {service_url}")
    
    if not re.match(r'^[a-zA-Z0-9\.-]+$', service_url):
        logger.error(f"Invalid characters in service URL: {service_url}")
        return {'status': 'error', 'output': 'Invalid service URL format.'}


    command = f"ping -c 3 {service_url}"
    
    try:
        output = subprocess.check_output(
            command, 
            shell=True, 
            stderr=subprocess.STDOUT, 
            text=True
        )
        return {'status': 'online', 'output': output}
    except subprocess.CalledProcessError as e:
        logger.warning(f"Service check failed for {service_url}: {e.output}")
        return {'status': 'offline', 'output': e.output}
    except Exception as e:
        logger.error(f"An unexpected error occurred during ping: {e}")
        return {'status': 'error', 'output': str(e)}

# --- Web Server Logic ---

class SimpleAPIHandler(BaseHTTPRequestHandler):
    """
    A very basic request handler to simulate API endpoints.
    """
    def do_GET(self):
        if self.path.startswith('/api/reports/'):
            # Example path: /api/reports/bob
            try:
                username = self.path.split('/')[-1]
                data = fetch_user_reports(username)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode('utf-8'))
            except Exception as e:
                self.send_error(500, str(e))
                
        elif self.path.startswith('/static/'):
            file_path = AppConfig.STATIC_CONTENT_DIR + self.path[len('/static/'):]
            
            if os.path.isfile(file_path):
                try:
                    self.send_response(200)
                    # Simple content type guessing
                    if file_path.endswith(".css"):
                        self.send_header('Content-type', 'text/css')
                    elif file_path.endswith(".js"):
                        self.send_header('Content-type', 'application/javascript')
                    else:
                        self.send_header('Content-type', 'application/octet-stream')
                    self.end_headers()
                    with open(file_path, 'rb') as f:
                        self.wfile.write(f.read())
                except Exception as e:
                    logger.error(f"Could not serve file {file_path}: {e}")
                    self.send_error(500, "Could not read file.")
            else:
                self.send_error(404, "File not found.")
                
        elif self.path.startswith('/admin/diag/'):
            # Example path: /admin/diag/google.com
            try:
                service = self.path.split('/')[-1]
                data = check_service_status(service)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode('utf-8'))
            except Exception as e:
                self.send_error(500, str(e))
        
        else:
            self.send_error(404, "Endpoint not found.")

def run_server(port=8080):
    """Starts the web server."""
    server_address = ('', port)
    httpd = HTTPServer(server_address, SimpleAPIHandler)
    logger.info(f"Starting simple API server on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    initialize_database()
    logger.info("Starting application...")

    logger.info(f"Using Analytics Key ID: {AppConfig.ANALYTICS_API_KEY[:8]}...")
    
    # Start the server
    run_server()