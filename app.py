from xml.parsers.expat import errors
import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import sys
import uuid
import json
from datetime import datetime
import requests
import base64
from urllib.parse import urlencode
import tarfile
import io
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from code_cleaner import compress_code

# Ensure project root is on sys.path so `SecureBYTE_AI` package is importable
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from SecureBYTE_AI.main import LLMManager
    LLM_AVAILABLE = True
    print("LLM Manager imported successfully")
except Exception as e:
    print(f"Warning: Could not import LLMManager: {e}")
    LLMManager = None
    LLM_AVAILABLE = False

# Get the database URL from environment variable
SERVICE_ACCOUNT_PATH = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if not SERVICE_ACCOUNT_PATH:
    raise RuntimeError('FIREBASE_SERVICE_ACCOUNT environment variable not set.')

cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
DATABASE_URL = "https://byte-b61ba-default-rtdb.firebaseio.com/"
firebase_admin.initialize_app(cred, {
    'databaseURL': DATABASE_URL
})

app = Flask(__name__)
# Match CORS setup from feature/CORS-secuirty-rev: allow all origins
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize Flask-Limiter
limiter = Limiter(
    key_func=get_remote_address,  # Rate limit by IP address
    default_limits=["200 per day", "50 per hour"]  # Global limits
)

limiter.init_app(app)

# GitHub OAuth configuration
GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET')
GITHUB_REDIRECT_URI = os.environ.get('GITHUB_REDIRECT_URI')

# Initialize LLM Manager if available
llm = None
if LLM_AVAILABLE and LLMManager:
    try:
        llm = LLMManager()
        print("LLM Manager initialized successfully")
    except Exception as e:
        print(f"Failed to initialize LLM Manager: {e}")
        llm = None

#prompt loader helper function
def load_prompt(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()



@app.route('/')
def home():
    return 'Welcome to SecureBYTE Backend!'

# Helper function to get current timestamp
def get_timestamp():
    return datetime.now().isoformat()

# Projects endpoints

@app.route('/users/<user_id>/projects', methods=['POST'])
def create_project(user_id):
    """Create a new project for a specific user"""
    data = request.json
    
    # Validate required fields
    if not data.get('project_name'):
        return jsonify({'error': 'project_name is required'}), 400
    
    # Generate project ID
    project_id = str(uuid.uuid4())
    
    # Prepare project data
    project_data = {
        'projectid': project_id,
        'project_name': data['project_name'],
        'project_desc': data.get('project_desc', ''),
        'fileids': [],  # Array of submission IDs
        'created_at': get_timestamp(),
        'updated_at': get_timestamp()
    }
    
    # Store in user-specific path
    ref = db.reference(f'users/{user_id}/projects/{project_id}')
    ref.set(project_data)
    
    return jsonify({
        'projectid': project_id,
        'message': 'Project created successfully'
    }), 201

@app.route('/users/<user_id>/projects', methods=['GET'])
def get_projects(user_id):
    """Get all projects for a specific user"""
    ref = db.reference(f'users/{user_id}/projects')
    projects = ref.get() or {}
    
    # Convert to list format
    result = list(projects.values())
    return jsonify(result)

@app.route('/users/<user_id>/projects/<project_id>', methods=['GET'])
def get_project(user_id, project_id):
    """Get a specific project"""
    ref = db.reference(f'users/{user_id}/projects/{project_id}')
    project = ref.get()
    
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    return jsonify(project)

@app.route('/users/<user_id>/projects/<project_id>', methods=['PUT'])
def update_project(user_id, project_id):
    """Update a project"""
    data = request.json
    
    # Add updated timestamp
    data['updated_at'] = get_timestamp()
    
    ref = db.reference(f'users/{user_id}/projects/{project_id}')
    
    # Check if project exists
    if not ref.get():
        return jsonify({'error': 'Project not found'}), 404
    
    ref.update(data)
    return jsonify({'message': 'Project updated successfully'})

@app.route('/users/<user_id>/projects/<project_id>', methods=['DELETE'])
def delete_project(user_id, project_id):
    """Delete a project and all its submissions"""
    project_ref = db.reference(f'users/{user_id}/projects/{project_id}')
    
    # Check if project exists
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Delete all submissions for this project
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    submissions = submissions_ref.get() or {}
    
    for submission_id, submission in submissions.items():
        if submission.get('projectid') == project_id:
            db.reference(f'users/{user_id}/submissions/{submission_id}').delete()
    
    # Delete the project
    project_ref.delete()
    
    return jsonify({'message': 'Project and related submissions deleted successfully'})

@app.route('/users/<user_id>/projects/<project_id>/save', methods=['PUT'])
def save_project(user_id, project_id):
    """Save (update) the files changed from the code editor"""
    data = request.json

    # Basic payload validation
    if not isinstance(data, list):
        return jsonify({'error': 'Request body must be a JSON array of files'}), 400

    project_ref = db.reference(f'users/{user_id}/projects/{project_id}')

    # Check if project exists
    if not project_ref.get():
        return jsonify({'error': 'Project not found'}), 404

    failed_files = []
    candidates = []  # Collect valid updates before applying (atomic behavior)

    # First pass: validate and stage updates
    try:
        for file_data in data:
            if not isinstance(file_data, dict):
                failed_files.append({'error': 'Invalid item type', 'item': file_data})
                continue
            file_id = file_data.get('fileid', '')
            filename = file_data.get('filename', '')
            code = file_data.get('code', '')

            if not file_id:
                failed_files.append({'fileid': file_id, 'filename': filename, 'error': 'fileid is required'})
                continue

            submission_ref = db.reference(f'users/{user_id}/submissions/{file_id}')
            submission = submission_ref.get()
            if not submission:
                failed_files.append({'fileid': file_id, 'filename': filename, 'error': 'Submission not found'})
                continue

            candidates.append({
                'ref': submission_ref,
                'update': {
                    'filename': filename,
                    'code': code,
                    'updated_at': get_timestamp()
                }
            })
    except Exception as e:
        failed_files.append({'error': str(e)})

    # If any files failed in validation, return error without applying any updates
    if failed_files:
        return jsonify({
            'error': 'Not all files could be saved',
            'failed_files': failed_files,
            'total_failed': len(failed_files),
            'total_files': len(data)
        }), 400

    # Second pass: apply all staged updates
    for item in candidates:
        item['ref'].update(item['update'])

    # Update project's updated_at timestamp
    project_ref.update({'updated_at': get_timestamp()})

    return jsonify({'message': 'Project saved successfully'})


# Submissions endpoints

@app.route('/users/<user_id>/projects/<project_id>/submissions', methods=['POST'])
def create_submission(user_id, project_id):
    """Create a new submission for a project"""
    data = request.json
    
    # Validate required fields
    if not data.get('filename'):
        return jsonify({'error': 'filename is required'}), 400
    
    # Check if project exists
    project_ref = db.reference(f'users/{user_id}/projects/{project_id}')
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Generate submission ID
    submission_id = str(uuid.uuid4())
    
    # Prepare submission data
    submission_data = {
        'id': submission_id,
        'projectid': project_id,
        'filename': data['filename'],
        'code': data.get('code', ''),
        'logicrev': data.get('logicrev', []),
        'testcases': data.get('testcases', []),
        'created_at': get_timestamp(),
        'updated_at': get_timestamp()
    }
    
    # Store submission
    submission_ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
    submission_ref.set(submission_data)
    
    # Update project's fileids array
    current_fileids = project.get('fileids', [])
    current_fileids.append(submission_id)
    project_ref.update({
        'fileids': current_fileids,
        'updated_at': get_timestamp()
    })
    
    return jsonify({
        'id': submission_id,
        'message': 'Submission created successfully'
    }), 201

@app.route('/users/<user_id>/projects/<project_id>/submissions', methods=['GET'])
def get_project_submissions(user_id, project_id):
    """Get all submissions for a specific project"""
    # Check if project exists
    project_ref = db.reference(f'users/{user_id}/projects/{project_id}')
    if not project_ref.get():
        return jsonify({'error': 'Project not found'}), 404
    
    # Get submissions for this project
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    all_submissions = submissions_ref.get() or {}
    
    # Filter submissions for this project
    project_submissions = []
    for submission_id, submission in all_submissions.items():
        if submission.get('projectid') == project_id:
            project_submissions.append(submission)
    
    return jsonify(project_submissions)

@app.route('/users/<user_id>/submissions/<submission_id>', methods=['GET'])
def get_submission(user_id, submission_id):
    """Get a specific submission"""
    ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
    submission = ref.get()
    
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    return jsonify(submission)

# Get only the code of a specific submission
@app.route('/users/<user_id>/submissions/<submission_id>/code', methods=['GET'])
def get_submission_code(user_id, submission_id):
    """Get only the code of a specific submission"""
    ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
    submission = ref.get()
    
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    print( "SUBMISSION CODE" , submission.get('code', ''))
    return jsonify({'code': submission.get('code', '')})

@app.route('/users/<user_id>/submissions/<submission_id>', methods=['PUT'])
def update_submission(user_id, submission_id):
    """Update a submission"""
    data = request.json
    
    # Add updated timestamp
    data['updated_at'] = get_timestamp()
    
    # Align with v2 schema: ignore deprecated fields on submissions
    for _deprecated in ['securityrev', 'reviewpdf']:
        if _deprecated in data:
            data.pop(_deprecated, None)
    
    ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
    
    # Check if submission exists
    if not ref.get():
        return jsonify({'error': 'Submission not found'}), 404
    
    ref.update(data)
    return jsonify({'message': 'Submission updated successfully'})

@app.route('/users/<user_id>/submissions/<submission_id>', methods=['DELETE'])
def delete_submission(user_id, submission_id):
    """Delete a submission"""
    submission_ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
    
    # Check if submission exists
    submission = submission_ref.get()
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404
    
    project_id = submission.get('projectid')
    
    # Remove submission ID from project's fileids
    if project_id:
        project_ref = db.reference(f'users/{user_id}/projects/{project_id}')
        project = project_ref.get()
        if project:
            fileids = project.get('fileids', [])
            if submission_id in fileids:
                fileids.remove(submission_id)
                project_ref.update({
                    'fileids': fileids,
                    'updated_at': get_timestamp()
                })
    
    # Delete the submission
    submission_ref.delete()
    
    return jsonify({'message': 'Submission deleted successfully'})


# History endpoints

@app.route('/users/<user_id>/history', methods=['GET'])
def get_user_history(user_id):
    """Get complete history of all user activities"""
    # Get all projects and submissions
    projects_ref = db.reference(f'users/{user_id}/projects')
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    
    projects = projects_ref.get() or {}
    submissions = submissions_ref.get() or {}
    
    # Create history entries
    history = []
    
    # Add project creation events
    for project_id, project in projects.items():
        history.append({
            'type': 'project_created',
            'id': project_id,
            'name': project.get('project_name', ''),
            'timestamp': project.get('created_at', ''),
            'description': project.get('project_desc', '')
        })
        
        # Add project update events
        if project.get('updated_at') and project.get('updated_at') != project.get('created_at'):
            history.append({
                'type': 'project_updated',
                'id': project_id,
                'name': project.get('project_name', ''),
                'timestamp': project.get('updated_at', ''),
                'description': project.get('project_desc', '')
            })
    
    # Add submission events
    for submission_id, submission in submissions.items():
        history.append({
            'type': 'submission_created',
            'id': submission_id,
            'project_id': submission.get('projectid', ''),
            'filename': submission.get('filename', ''),
            'timestamp': submission.get('created_at', '')
        })
        
        # Add submission update events
        if submission.get('updated_at') and submission.get('updated_at') != submission.get('created_at'):
            history.append({
                'type': 'submission_updated',
                'id': submission_id,
                'project_id': submission.get('projectid', ''),
                'filename': submission.get('filename', ''),
                'timestamp': submission.get('updated_at', '')
            })
    
    # Sort by timestamp (newest first)
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(history)

@app.route('/users/<user_id>/projects/<project_id>/history', methods=['GET'])
def get_project_history(user_id, project_id):
    """Get history for a specific project"""
    # Check if project exists
    project_ref = db.reference(f'users/{user_id}/projects/{project_id}')
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Get all submissions for this project
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    all_submissions = submissions_ref.get() or {}
    
    history = []
    
    # Add project events
    history.append({
        'type': 'project_created',
        'id': project_id,
        'name': project.get('project_name', ''),
        'timestamp': project.get('created_at', ''),
        'description': project.get('project_desc', '')
    })
    
    if project.get('updated_at') and project.get('updated_at') != project.get('created_at'):
        history.append({
            'type': 'project_updated',
            'id': project_id,
            'name': project.get('project_name', ''),
            'timestamp': project.get('updated_at', ''),
            'description': project.get('project_desc', '')
        })
    
    # Add submission events for this project
    for submission_id, submission in all_submissions.items():
        if submission.get('projectid') == project_id:
            history.append({
                'type': 'submission_created',
                'id': submission_id,
                'filename': submission.get('filename', ''),
                'timestamp': submission.get('created_at', '')
            })
            
            if submission.get('updated_at') and submission.get('updated_at') != submission.get('created_at'):
                history.append({
                    'type': 'submission_updated',
                    'id': submission_id,
                    'filename': submission.get('filename', ''),
                    'timestamp': submission.get('updated_at', '')
                })
    
    # Sort by timestamp (newest first)
    history.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return jsonify(history)

# Metrics endpoints

@app.route('/users/<user_id>/metrics', methods=['GET'])
def get_user_metrics(user_id):
    """Get comprehensive metrics for a user"""
    projects_ref = db.reference(f'users/{user_id}/projects')
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    
    projects = projects_ref.get() or {}
    submissions = submissions_ref.get() or {}
    
    # Calculate metrics
    total_projects = len(projects)
    total_submissions = len(submissions)
    
    # Count security and logic reviews
    total_security_reviews = 0
    total_logic_reviews = 0
    total_test_cases = 0
    
    # Count issues by severity
    severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    
    for submission in submissions.values():
        # Count reviews
        if submission.get('securityrev'):
            total_security_reviews += len(submission['securityrev'])
            # Parse security reviews for severity counts
            for review in submission['securityrev']:
                try:
                    if isinstance(review, str):
                        import json
                        review_data = json.loads(review)
                        for file_data in review_data.get('files', []):
                            for issue in file_data.get('issues', []):
                                severity = issue.get('severity', {}).get('level', 'low')
                                if severity in severity_counts:
                                    severity_counts[severity] += 1
                except:
                    pass
        
        if submission.get('logicrev'):
            total_logic_reviews += len(submission['logicrev'])
        
        if submission.get('testcases'):
            total_test_cases += len(submission['testcases'])
    
    # Calculate average issues per submission
    avg_issues_per_submission = 0
    if total_submissions > 0:
        total_issues = sum(severity_counts.values())
        avg_issues_per_submission = total_issues / total_submissions
    
    # Get recent activity (last 30 days)
    from datetime import datetime, timedelta
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    
    recent_projects = 0
    recent_submissions = 0
    
    for project in projects.values():
        if project.get('created_at', '') >= thirty_days_ago:
            recent_projects += 1
    
    for submission in submissions.values():
        if submission.get('created_at', '') >= thirty_days_ago:
            recent_submissions += 1
    
    metrics = {
        'total_projects': total_projects,
        'total_submissions': total_submissions,
        'total_security_reviews': total_security_reviews,
        'total_logic_reviews': total_logic_reviews,
        'total_test_cases': total_test_cases,
        'severity_distribution': severity_counts,
        'avg_issues_per_submission': round(avg_issues_per_submission, 2),
        'recent_activity': {
            'projects_last_30_days': recent_projects,
            'submissions_last_30_days': recent_submissions
        }
    }
    
    return jsonify(metrics)

@app.route('/users/<user_id>/projects/<project_id>/metrics', methods=['GET'])
def get_project_metrics(user_id, project_id):
    """Get metrics for a specific project"""
    # Check if project exists
    project_ref = db.reference(f'users/{user_id}/projects/{project_id}')
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Get submissions for this project
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    all_submissions = submissions_ref.get() or {}
    
    project_submissions = []
    for submission_id, submission in all_submissions.items():
        if submission.get('projectid') == project_id:
            project_submissions.append(submission)
    
    # Calculate project-specific metrics
    total_submissions = len(project_submissions)
    total_security_reviews = 0
    total_logic_reviews = 0
    total_test_cases = 0
    
    severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    
    for submission in project_submissions:
        if submission.get('securityrev'):
            total_security_reviews += len(submission['securityrev'])
            # Parse security reviews for severity counts
            for review in submission['securityrev']:
                try:
                    if isinstance(review, str):
                        import json
                        review_data = json.loads(review)
                        for file_data in review_data.get('files', []):
                            for issue in file_data.get('issues', []):
                                severity = issue.get('severity', {}).get('level', 'low')
                                if severity in severity_counts:
                                    severity_counts[severity] += 1
                except:
                    pass
        
        if submission.get('logicrev'):
            total_logic_reviews += len(submission['logicrev'])
        
        if submission.get('testcases'):
            total_test_cases += len(submission['testcases'])
    
    # Calculate average issues per submission
    avg_issues_per_submission = 0
    if total_submissions > 0:
        total_issues = sum(severity_counts.values())
        avg_issues_per_submission = total_issues / total_submissions
    
    metrics = {
        'project_name': project.get('project_name', ''),
        'project_description': project.get('project_desc', ''),
        'total_submissions': total_submissions,
        'total_security_reviews': total_security_reviews,
        'total_logic_reviews': total_logic_reviews,
        'total_test_cases': total_test_cases,
        'severity_distribution': severity_counts,
        'avg_issues_per_submission': round(avg_issues_per_submission, 2),
        'created_at': project.get('created_at', ''),
        'updated_at': project.get('updated_at', '')
    }
    
    return jsonify(metrics)

# Dashboard endpoints

@app.route('/users/<user_id>/dashboard', methods=['GET'])
def get_user_dashboard(user_id):
    """Get comprehensive dashboard data for a user"""
    projects_ref = db.reference(f'users/{user_id}/projects')
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    
    projects = projects_ref.get() or {}
    submissions = submissions_ref.get() or {}
    
    # Get recent projects (last 5)
    recent_projects = []
    for project_id, project in projects.items():
        recent_projects.append({
            'id': project_id,
            'name': project.get('project_name', ''),
            'description': project.get('project_desc', ''),
            'submission_count': len(project.get('fileids', [])),
            'created_at': project.get('created_at', ''),
            'updated_at': project.get('updated_at', '')
        })
    
    # Sort by updated_at (most recent first) and take top 5
    recent_projects.sort(key=lambda x: x['updated_at'], reverse=True)
    recent_projects = recent_projects[:5]
    
    # Get recent submissions (last 10)
    recent_submissions = []
    for submission_id, submission in submissions.items():
        recent_submissions.append({
            'id': submission_id,
            'project_id': submission.get('projectid', ''),
            'filename': submission.get('filename', ''),
            'created_at': submission.get('created_at', ''),
            'updated_at': submission.get('updated_at', ''),
            'has_security_review': len(submission.get('securityrev', [])) > 0,
            'has_logic_review': len(submission.get('logicrev', [])) > 0,
            'has_test_cases': len(submission.get('testcases', [])) > 0
        })
    
    # Sort by updated_at (most recent first) and take top 10
    recent_submissions.sort(key=lambda x: x['updated_at'], reverse=True)
    recent_submissions = recent_submissions[:10]
    
    # Calculate quick stats
    total_projects = len(projects)
    total_submissions = len(submissions)
    
    # Count reviews
    total_security_reviews = sum(len(s.get('securityrev', [])) for s in submissions.values())
    total_logic_reviews = sum(len(s.get('logicrev', [])) for s in submissions.values())
    total_test_cases = sum(len(s.get('testcases', [])) for s in submissions.values())
    
    # Get activity in last 7 days
    from datetime import datetime, timedelta
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    recent_activity = {
        'projects_created': sum(1 for p in projects.values() if p.get('created_at', '') >= seven_days_ago),
        'submissions_created': sum(1 for s in submissions.values() if s.get('created_at', '') >= seven_days_ago)
    }
    
    dashboard_data = {
        'quick_stats': {
            'total_projects': total_projects,
            'total_submissions': total_submissions,
            'total_security_reviews': total_security_reviews,
            'total_logic_reviews': total_logic_reviews,
            'total_test_cases': total_test_cases
        },
        'recent_activity': recent_activity,
        'recent_projects': recent_projects,
        'recent_submissions': recent_submissions
    }
    
    return jsonify(dashboard_data)

@app.route('/users/<user_id>/dashboard/summary', methods=['GET'])
def get_dashboard_summary(user_id):
    """Get a quick summary for the dashboard"""
    projects_ref = db.reference(f'users/{user_id}/projects')
    submissions_ref = db.reference(f'users/{user_id}/submissions')
    
    projects = projects_ref.get() or {}
    submissions = submissions_ref.get() or {}
    
    # Calculate summary stats
    total_projects = len(projects)
    total_submissions = len(submissions)
    
    # Count issues by severity across all submissions
    severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    
    for submission in submissions.values():
        for review in submission.get('securityrev', []):
            try:
                if isinstance(review, str):
                    import json
                    review_data = json.loads(review)
                    for file_data in review_data.get('files', []):
                        for issue in file_data.get('issues', []):
                            severity = issue.get('severity', {}).get('level', 'low')
                            if severity in severity_counts:
                                severity_counts[severity] += 1
            except:
                pass
    
    # Get most critical issues (top 3)
    critical_issues = []
    for submission in submissions.values():
        for review in submission.get('securityrev', []):
            try:
                if isinstance(review, str):
                    import json
                    review_data = json.loads(review)
                    for file_data in review_data.get('files', []):
                        for issue in file_data.get('issues', []):
                            if issue.get('severity', {}).get('level') in ['critical', 'high']:
                                critical_issues.append({
                                    'filename': file_data.get('filename', ''),
                                    'line': issue.get('line', 0),
                                    'feedback': issue.get('feedback', ''),
                                    'severity': issue.get('severity', {}).get('level', ''),
                                    'submission_id': submission.get('id', '')
                                })
            except:
                pass
    
    # Sort by severity and take top 3
    critical_issues.sort(key=lambda x: {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}.get(x['severity'], 0), reverse=True)
    critical_issues = critical_issues[:3]
    
    summary = {
        'total_projects': total_projects,
        'total_submissions': total_submissions,
        'total_issues': sum(severity_counts.values()),
        'severity_breakdown': severity_counts,
        'critical_issues': critical_issues
    }
    
    return jsonify(summary)

# Common Route handler for LLM reviews 

def handle_llm_review(review_type, user_id, project_or_submission_id, data):
    """Handle LLM review requests"""

    PROMPT_PATHS = {
        "logic": "prompts/logic_prompt.txt",
        "testing": "prompts/testing_prompt.txt",
        "security": "prompts/security_prompt.txt"
    }

    if review_type not in PROMPT_PATHS:
        return {"success": False, "error": "Invalid review type"}

    if review_type == "security":
        # For security reviews, data is an array of files
        files_data = data
        if not files_data or len(files_data) == 0:
            return {"success": False, "error": "Missing files data"}
        
        for file_data in files_data:
            original_code = file_data.get('code', '')

            # Clean the code before sending to LLM
            cleaned_code = compress_code(original_code)
           
            file_data['code'] = cleaned_code

        # Convert the files array to JSON string for the prompt
        code = json.dumps(files_data, indent=2)
        
    else:
        # For logic and testing reviews, data has a 'code' field
        original_code = data.get('code', '')

        # Clean the code before sending to LLM
        code = compress_code(original_code)

        if not code:
            return {"success": False, "error": "Missing 'code'"}

    if llm is None:
        return {"success": False, "error": "LLM not available on server"}

    try:   
        # Load the correct prompt template for the review type
        prompt_template = load_prompt(PROMPT_PATHS[review_type])

        # Inject the code into the template
        prompt = prompt_template.replace('{code}', code)

        # Generate response from LLM
        response = llm.generate_response(user_prompt=prompt)
        print(f"response: {response}")

        # Handle both string and generator responses
        if hasattr(response, 'system_prompt'):
            full_response = ''.join(response.system_prompt)
        else:
            full_response = str(response)

        return full_response
        
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Route for logic review
@app.route('/users/<user_id>/submissions/<submission_id>/logic-review', methods=['POST'])
@limiter.limit("1 per 5 seconds") 
def logic_review(user_id, submission_id):

    # Update the submission to be the latest version

    update_submission(user_id, submission_id)

    ref = db.reference(f'users/{user_id}/submissions/{submission_id}')

    # Check if submission exists
    submission_data = ref.get()
    if not submission_data:
        return jsonify({'error': 'Submission not found'}), 404

    #get response from llm
    llm_review = handle_llm_review("logic", user_id, submission_id, request.get_json())

    try:
        llm_review_obj = json.loads(llm_review)
    except json.JSONDecodeError:
        return jsonify({'error': 'Prompt returned NOT a valid JSON'}), 500

    # Append new review
    logic_rev = submission_data.get('logicrev', [])
    logic_rev.append({
        "review": llm_review_obj    
    })
    ref.update({
        "logicrev": logic_rev
    })

    return jsonify({
        "success": True,
        "review_type": "logic",
        "user_id": user_id,
        "submission_id": submission_id,
        "response": llm_review_obj
    })

# Route for testing review
@app.route('/users/<user_id>/submissions/<submission_id>/testing-review', methods=['POST'])
@limiter.limit("1 per 5 seconds") 
def testing_review(user_id, submission_id):
    
    # Update the submission to be the latest version
    update_submission(user_id, submission_id)
    
    ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
    
    # Check if submission exists
    submission_data = ref.get()
    if not submission_data:
        return jsonify({'error': 'Submission not found'}), 404

    llm_review = handle_llm_review("testing", user_id, submission_id, request.get_json())

    try:
        llm_review_obj = json.loads(llm_review)
    except json.JSONDecodeError:
        return jsonify({'error': 'Prompt returned NOT a valid JSON'}), 500

    # Append new review 
    test_rev = submission_data.get('testingrev', [])
    test_rev.append({
        "review": llm_review_obj
    })
    ref.update({
        "testingrev": test_rev
    })

    return jsonify({
        "success": True,
        "review_type": "testing",
        "user_id": user_id,
        "submission_id": submission_id,
        "response": llm_review_obj
    })

# Route for security review 
@app.route('/users/<user_id>/projects/<project_id>/security-review', methods=['POST'])
@limiter.limit("1 per 5 seconds") 
def security_review(user_id, project_id):

    ref = db.reference(f'users/{user_id}/projects/{project_id}')

    # Function to update the database with the newest submission needs implementation
    
    # Check if project exists
    project_data = ref.get()
    if not project_data:
        return jsonify({'error': 'Project not found'}), 404
    
    #extract a list of fileids to be sent to LLM 
    file_ids = project_data.get('fileids', [])

    # Extract code, filename for each file ID
    data = []
    for file_id in file_ids:
        submission_ref = db.reference(f'users/{user_id}/submissions/{file_id}')
        submission_data = submission_ref.get()
        if submission_data:
            data.append({
            'filename': submission_data.get('filename', ''),
            'code': submission_data.get('code', '')
        })
    
    llm_review = handle_llm_review("security", user_id, project_id, data)

    try:
        llm_review_obj = json.loads(llm_review)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON returned from LLM'}), 500

    # Append new review
    sec_rev = project_data.get('securityrev', [])
    sec_rev.append({
        "review": llm_review_obj
    })
    ref.update({
        "securityrev": sec_rev
    })  

    return jsonify({
        "success": True,
        "review_type": "security",
        "user_id": user_id,
        "project_id": project_id,
        "response": llm_review_obj
    })


# ===== GitHub Integration =====
def extract_github_token():
    auth_header = request.headers.get('Authorization', '')
    if isinstance(auth_header, str) and auth_header.startswith('Bearer '):
        return auth_header[7:]
    token = request.args.get('access_token')
    if not token:
        json_data = request.get_json(silent=True) or {}
        token = json_data.get('access_token')
    return token

def github_headers(token):
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }

@app.route('/auth/github/exchange-token', methods=['POST'])
def github_exchange_token():
    data = request.get_json(silent=True) or {}
    code = data.get('code')
    redirect_uri = data.get('redirect_uri') or GITHUB_REDIRECT_URI
    if not code:
        return jsonify({'error': 'code is required'}), 400
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        return jsonify({'error': 'Server missing GitHub OAuth configuration'}), 500
    try:
        resp = requests.post(
            'https://github.com/login/oauth/access_token',
            headers={'Accept': 'application/json'},
            data={
                'client_id': GITHUB_CLIENT_ID,
                'client_secret': GITHUB_CLIENT_SECRET,
                'code': code,
                'redirect_uri': redirect_uri
            },
            timeout=15
        )
        resp.raise_for_status()
        payload = resp.json()
        if 'error' in payload:
            return jsonify({'error': payload.get('error_description') or payload.get('error')}), 400
        return jsonify({
            'access_token': payload.get('access_token'),
            'token_type': payload.get('token_type'),
            'scope': payload.get('scope')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/users/<user_id>/github/repos', methods=['GET'])
def list_github_repos(user_id):
    token = extract_github_token()
    if not token:
        return jsonify({'error': 'Missing GitHub access token'}), 401
    per_page = request.args.get('per_page', default=100, type=int)
    page = request.args.get('page', default=1, type=int)
    try:
        resp = requests.get(
            f'https://api.github.com/user/repos',
            headers=github_headers(token),
            params={'per_page': per_page, 'page': page, 'sort': 'updated'},
            timeout=15
        )
        if resp.status_code == 401:
            return jsonify({'error': 'Invalid GitHub token'}), 401
        resp.raise_for_status()
        repos = resp.json()
        simplified = []
        for r in repos:
            simplified.append({
                'id': r.get('id'),
                'name': r.get('name'),
                'full_name': r.get('full_name'),
                'private': r.get('private'),
                'default_branch': r.get('default_branch'),
                'permissions': r.get('permissions'),
                'html_url': r.get('html_url'),
                'language': r.get('language'),
                'updated_at': r.get('updated_at'),
                'owner': {
                    'login': (r.get('owner') or {}).get('login')
                }
            })
        return jsonify(simplified)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_project_ref(user_id, project_id):
    return db.reference(f'users/{user_id}/projects/{project_id}')

def get_submission_ref(user_id, submission_id):
    return db.reference(f'users/{user_id}/submissions/{submission_id}')

def is_supported_text_file(path):
    lower = path.lower()
    extensions = [
        '.js', '.jsx', '.ts', '.tsx', '.py', '.ipynb', '.java', '.go', '.rb', '.php', '.c', '.cpp', '.h', '.hpp',
        '.cs', '.rs', '.kt', '.swift', '.m', '.scala', '.sh', '.bat', '.ps1', '.sql', '.json', '.yml', '.yaml',
        '.toml', '.ini', '.cfg', '.conf', '.properties', '.xml', '.html', '.css', '.scss', '.less', '.vue',
        '.svelte', '.gradle', '.md', '.txt', '.env', '.gitignore', '.gitattributes', '.editorconfig'
    ]
    if any(lower.endswith(ext) for ext in extensions):
        return True
    # Common filenames without extensions
    basename = lower.split('/')[-1]
    if basename in ['makefile', 'dockerfile', 'license', 'readme']:
        return True
    return False

def normalize_relative_path(path: str) -> str:
    """
    Normalize a user-supplied relative path. Reject absolute paths or traversal.
    Returns a posix-style path (forward slashes).
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Empty path")
    candidate = path.replace('\\', '/').lstrip('./').lstrip('/')
    norm = os.path.normpath(candidate)
    if os.path.isabs(norm) or norm.startswith('..'):
        raise ValueError("Invalid path")
    return norm.replace(os.sep, '/')

@app.route('/users/<user_id>/projects/<project_id>/submissions/batch', methods=['POST'])
def create_submissions_batch(user_id, project_id):
    """
    JSON batch upload.
    Body: { "files": [{"path": "src/index.js", "content": "..."}, ...], "max_files"?: int, "max_bytes"?: int }
    """
    data = request.get_json(silent=True) or {}
    files = data.get('files') or []
    max_files = data.get('max_files')
    max_bytes = data.get('max_bytes')

    if not isinstance(files, list) or len(files) == 0:
        return jsonify({'error': 'files must be a non-empty array'}), 400

    project_ref = get_project_ref(user_id, project_id)
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    created = 0
    created_ids = []
    fileids = project.get('fileids', [])

    for f in files:
        raw_path = (f or {}).get('path') or (f or {}).get('filename')
        content = (f or {}).get('content')
        if content is None:
            content = (f or {}).get('code', '')
        if not raw_path:
            continue
        try:
            relpath = normalize_relative_path(raw_path)
        except ValueError:
            continue

        try:
            size_bytes = len((content or '').encode('utf-8', errors='ignore'))
        except Exception:
            size_bytes = 0
        if isinstance(max_bytes, int) and max_bytes > 0 and size_bytes > max_bytes:
            continue

        submission_id = str(uuid.uuid4())
        submission_data = {
            'id': submission_id,
            'projectid': project_id,
            'filename': relpath,
            'code': content or '',
            'logicrev': [],
            'testcases': [],
            'created_at': get_timestamp(),
            'updated_at': get_timestamp()
        }
        get_submission_ref(user_id, submission_id).set(submission_data)
        fileids.append(submission_id)
        created_ids.append(submission_id)
        created += 1

        if isinstance(max_files, int) and max_files > 0 and created >= max_files:
            break

    project_ref.update({'fileids': fileids, 'updated_at': get_timestamp()})
    return jsonify({'message': 'Batch upload complete', 'created': created, 'created_ids': created_ids}), 201

@app.route('/users/<user_id>/projects/<project_id>/submissions/upload', methods=['POST'])
def upload_submissions_multipart(user_id, project_id):
    """
    Multipart upload.
    Expect fields:
      - files: multiple file parts (name='files')
      - relative_paths: JSON array of paths aligned to files (optional)
      - max_files: optional int
      - max_bytes: optional int (per-file cap)
    """
    project_ref = get_project_ref(user_id, project_id)
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    storage_files = request.files.getlist('files')
    rel_paths_raw = request.form.get('relative_paths', '')
    try:
        rel_paths = json.loads(rel_paths_raw) if rel_paths_raw else []
        if not isinstance(rel_paths, list):
            rel_paths = []
    except Exception:
        rel_paths = []

    max_files = request.form.get('max_files', type=int)
    max_bytes = request.form.get('max_bytes', type=int)

    created = 0
    created_ids = []
    fileids = project.get('fileids', [])

    for idx, storage in enumerate(storage_files):
        if not storage:
            continue
        proposed_path = rel_paths[idx] if idx < len(rel_paths) else storage.filename
        try:
            relpath = normalize_relative_path(proposed_path)
        except ValueError:
            continue

        data_bytes = storage.read() or b''
        if isinstance(max_bytes, int) and max_bytes > 0 and len(data_bytes) > max_bytes:
            continue
        try:
            code_str = data_bytes.decode('utf-8', errors='replace')
        except Exception:
            code_str = ''

        submission_id = str(uuid.uuid4())
        submission_data = {
            'id': submission_id,
            'projectid': project_id,
            'filename': relpath,
            'code': code_str,
            'logicrev': [],
            'testcases': [],
            'created_at': get_timestamp(),
            'updated_at': get_timestamp()
        }
        get_submission_ref(user_id, submission_id).set(submission_data)
        fileids.append(submission_id)
        created_ids.append(submission_id)
        created += 1

        if isinstance(max_files, int) and max_files > 0 and created >= max_files:
            break

    project_ref.update({'fileids': fileids, 'updated_at': get_timestamp()})
    return jsonify({'message': 'Upload complete', 'created': created, 'created_ids': created_ids}), 201

@app.route('/users/<user_id>/projects/<project_id>/github/link', methods=['POST'])
def link_github_repo(user_id, project_id):
    data = request.get_json(silent=True) or {}
    repo_full_name = data.get('repo_full_name')
    branch = data.get('branch')
    token = extract_github_token()

    project_ref = get_project_ref(user_id, project_id)
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    if not repo_full_name:
        return jsonify({'error': 'repo_full_name is required'}), 400

    default_branch = None
    if token:
        try:
            check = requests.get(
                f'https://api.github.com/repos/{repo_full_name}',
                headers=github_headers(token),
                timeout=15
            )
            if check.status_code == 404:
                return jsonify({'error': 'Repository not found'}), 404
            if check.status_code == 401:
                return jsonify({'error': 'Invalid GitHub token'}), 401
            check.raise_for_status()
            default_branch = (check.json() or {}).get('default_branch')
        except Exception as e:
            return jsonify({'error': f'Failed to verify repo: {str(e)}'}), 502

    if not branch:
        branch = default_branch or 'main'

    github_link = {
        'repo_full_name': repo_full_name,
        'branch': branch,
        'linked_at': get_timestamp()
    }
    project_ref.update({'github': github_link, 'updated_at': get_timestamp()})
    return jsonify({'message': 'Repository linked', 'github': github_link})

@app.route('/users/<user_id>/projects/<project_id>/github/import', methods=['POST'])
def import_github_repo(user_id, project_id):
    print(f"[IMPORT] Starting import for user={user_id}, project={project_id}")
    token = extract_github_token()
    if not token:
        print("[IMPORT] No GitHub token found")
        return jsonify({'error': 'Missing GitHub access token'}), 401
    
    print(f"[IMPORT] Using GitHub token: {token[:10]}..." if token else "[IMPORT] No token")

    data = request.get_json(silent=True) or {}
    repo_full_name = data.get('repo_full_name')
    branch = data.get('branch')
    max_files = data.get('max_files')  # No hard cap unless provided
    # No size restriction by default; only apply if provided
    max_bytes = data.get('max_bytes')

    project_ref = get_project_ref(user_id, project_id)
    project = project_ref.get()
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    if not repo_full_name:
        linked = project.get('github') or {}
        repo_full_name = linked.get('repo_full_name')
    if not repo_full_name:
        return jsonify({'error': 'repo_full_name is required (or link the project first)'}), 400

    if not branch:
        # Prefer linked branch if available, else repo default
        linked = project.get('github') or {}
        branch = linked.get('branch')
        if not branch:
            repo_resp = requests.get(
                f'https://api.github.com/repos/{repo_full_name}',
                headers=github_headers(token),
                timeout=15
            )
            if repo_resp.status_code == 200:
                branch = (repo_resp.json() or {}).get('default_branch') or 'main'
            else:
                branch = 'main'

    if not repo_full_name:
        return jsonify({'error': 'repo_full_name is required (or link the project first)'}), 400

    try:
        tree_url = f'https://api.github.com/repos/{repo_full_name}/git/trees/{branch}'
        print(f"[IMPORT] Fetching tree from: {tree_url}")
        tree_resp = requests.get(
            tree_url,
            headers=github_headers(token),
            params={'recursive': '1'},
            timeout=20
        )
        print(f"[IMPORT] Tree API response status: {tree_resp.status_code}")
        if tree_resp.status_code == 404:
            # Fallback to the repo default branch if provided branch not found
            repo_resp = requests.get(
                f'https://api.github.com/repos/{repo_full_name}',
                headers=github_headers(token),
                timeout=15
            )
            if repo_resp.status_code == 200:
                default_branch = (repo_resp.json() or {}).get('default_branch') or 'main'
                tree_resp = requests.get(
                    f'https://api.github.com/repos/{repo_full_name}/git/trees/{default_branch}',
                    headers=github_headers(token),
                    params={'recursive': '1'},
                    timeout=20
                )
                branch = default_branch
            else:
                return jsonify({'error': 'Repository or branch not found'}), 404
        if tree_resp.status_code == 401:
            return jsonify({'error': 'Invalid GitHub token'}), 401
        tree_resp.raise_for_status()
        tree_payload = tree_resp.json()
        tree = tree_payload.get('tree', [])
        truncated = bool(tree_payload.get('truncated'))
        print(f"[IMPORT] Got {len(tree)} items from tree API, truncated={truncated}")

        created = 0
        fileids = project.get('fileids', [])
        for node in tree:
            if node.get('type') != 'blob':
                print(f"[IMPORT] Skipping non-blob: {node.get('path')} (type: {node.get('type')})")
                continue
            path = node.get('path') or ''
            size = node.get('size') or 0
            print(f"[IMPORT] Processing file: {path} (size={size})")
            if max_bytes and size and size > max_bytes:
                print(f"[IMPORT] Skipping {path} - too large ({size} bytes)")
                continue
            # Import all files regardless of extension

            blob_sha = node.get('sha')
            print(f"[IMPORT] Fetching blob for {path} (sha: {blob_sha})")
            blob_resp = requests.get(
                f'https://api.github.com/repos/{repo_full_name}/git/blobs/{blob_sha}',
                headers=github_headers(token),
                timeout=20
            )
            # GitHub might return truncated content via the content API; ensure full blob fetch
            if blob_resp.status_code != 200:
                print(f"[IMPORT] Failed to get blob for {path}, status: {blob_resp.status_code}")
                continue
            blob = blob_resp.json()
            if blob.get('encoding') == 'base64':
                try:
                    # GitHub returns base64 content with newlines that need to be removed
                    content_b64 = (blob.get('content') or '').replace('\n', '').replace('\r', '')
                    content_bytes = base64.b64decode(content_b64, validate=True)
                    code_str = content_bytes.decode('utf-8', errors='replace')
                    print(f"[IMPORT] Decoded base64 content for {path} ({len(code_str)} chars)")
                except Exception as e:
                    print(f"[IMPORT] Failed to decode base64 for {path}: {str(e)}")
                    continue
            else:
                # Some endpoints may return raw content; try to treat it as text
                code_str = str(blob.get('content', ''))
                print(f"[IMPORT] Got raw content for {path} ({len(code_str)} chars)")

            submission_id = str(uuid.uuid4())
            submission_data = {
                'id': submission_id,
                'projectid': project_id,
                'filename': path,
                'code': code_str,
                'logicrev': [],
                'testcases': [],
                'created_at': get_timestamp(),
                'updated_at': get_timestamp()
            }
            get_submission_ref(user_id, submission_id).set(submission_data)
            fileids.append(submission_id)
            created += 1
            print(f"[IMPORT] Created submission {submission_id} for {path}")

            if max_files and created >= max_files:
                print(f"[IMPORT] Hit max_files limit ({max_files}), stopping")
                break
        # If Git tree was truncated, fall back to tarball to capture remaining files
        if truncated:
            try:
                tar_url = f'https://api.github.com/repos/{repo_full_name}/tarball/{branch}'
                tar_resp = requests.get(tar_url, headers=github_headers(token), stream=True, timeout=60)
                if tar_resp.status_code == 200:
                    tar_resp.raw.decode_content = True
                    with tarfile.open(fileobj=tar_resp.raw, mode='r|*') as tar:
                        for member in tar:
                            if not member.isreg():
                                continue
                            # member.name includes a top-level folder; strip it
                            parts = member.name.split('/', 1)
                            path = parts[1] if len(parts) > 1 else parts[0]
                            # Skip if already imported from the tree API loop
                            if any(sid for sid in fileids if path == db.reference(f'users/{user_id}/submissions/{sid}').get().get('filename')):
                                continue
                            fileobj = tar.extractfile(member)
                            if not fileobj:
                                continue
                            try:
                                content_bytes = fileobj.read()
                                code_str = content_bytes.decode('utf-8', errors='replace')
                            except Exception:
                                continue
                            submission_id = str(uuid.uuid4())
                            submission_data = {
                                'id': submission_id,
                                'projectid': project_id,
                                'filename': path,
                                'code': code_str,
                                'logicrev': [],
                                'testcases': [],
                                'created_at': get_timestamp(),
                                'updated_at': get_timestamp()
                            }
                            get_submission_ref(user_id, submission_id).set(submission_data)
                            fileids.append(submission_id)
                            created += 1
                            if max_files and created >= max_files:
                                break
                else:
                    # If tar fallback fails, proceed with what we have
                    pass
            except Exception:
                # Ignore tar fallback errors; return what we imported
                pass

        project_ref.update({'fileids': fileids, 'updated_at': get_timestamp()})
        print(f"[IMPORT] Import complete: {created} files imported, updating project fileids")
        return jsonify({'message': 'Import complete', 'files_imported': created, 'truncated_fallback_used': truncated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)