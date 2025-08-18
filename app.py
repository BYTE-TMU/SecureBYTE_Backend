import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import sys
import uuid
import json
from datetime import datetime

# Add the SecureBYTE_AI directory to the Python path
securebyte_ai_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'SecureBYTE_AI'))
if securebyte_ai_path not in sys.path:
    sys.path.insert(0, securebyte_ai_path)

try:
    from SecureBYTE_AI.main import LLMManager
    LLM_AVAILABLE = True
except ImportError as e:
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
CORS(app)

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
        'securityrev': data.get('securityrev', []),
        'logicrev': data.get('logicrev', []),
        'testcases': data.get('testcases', []),
        'reviewpdf': data.get('reviewpdf', ''),
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

@app.route('/users/<user_id>/submissions/<submission_id>', methods=['PUT'])
def update_submission(user_id, submission_id):
    """Update a submission"""
    data = request.json
    
    # Add updated timestamp
    data['updated_at'] = get_timestamp()
    
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
    code = data.get('code')       

    if not code:
        return jsonify({"success": False, "error": "Missing 'code'"}), 400

    PROMPT_PATHS = {
        "logic": "prompts/logic_prompt.txt",
        "testing": "prompts/testing_prompt.txt",
        "security": "prompts/security_prompt.txt"
    }

    if review_type not in PROMPT_PATHS:
        return jsonify({"success": False, "error": "Invalid review type"}), 400
    
    try:   
        # Load the correct prompt template for the review type
        prompt_template = load_prompt(PROMPT_PATHS[review_type])

        # Inject the code into the template
        prompt = prompt_template.format(code=code)

        # Generate response from LLM
        response = llm.generate_response(user_prompt=prompt)

        # Join all streamed chunks into a single string if given as a chunk 
        full_response = ''.join(response.system_prompt)

        return full_response
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Route for logic review
@app.route('/users/<user_id>/submissions/<submission_id>/logic-review', methods=['POST'])
def logic_review(user_id, submission_id):

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
        return jsonify({'error': 'Invalid JSON returned from LLM'}), 500

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

# Route for test case review
@app.route('/users/<user_id>/submissions/<submission_id>/testing-review', methods=['POST'])
def testing_review(user_id, submission_id):
    
    ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
    
    # Check if submission exists
    submission_data = ref.get()
    if not submission_data:
        return jsonify({'error': 'Submission not found'}), 404

    llm_review = handle_llm_review("testing", user_id, submission_id, request.get_json())

    try:
        llm_review_obj = json.loads(llm_review)
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON returned from LLM'}), 500

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
def security_review(user_id, project_id):

    ref = db.reference(f'users/{user_id}/projects/{project_id}')
    
    # Check if project exists
    project_data = ref.get()
    if not project_data:
        return jsonify({'error': 'Project not found'}), 404
    
    llm_review = handle_llm_review("security", user_id, project_id, request.get_json())

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


if __name__ == '__main__':
    app.run(debug=True)
