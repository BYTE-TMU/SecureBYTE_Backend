import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import uuid
from datetime import datetime

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

if __name__ == '__main__':
    app.run(debug=True)
