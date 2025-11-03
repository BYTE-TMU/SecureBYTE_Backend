import json
import os
import pytest
from datetime import datetime, timedelta


# Ensure required env var is set to avoid initialization failure in app import
os.environ.setdefault('FIREBASE_SERVICE_ACCOUNT', os.path.join(os.path.dirname(__file__), 'dummy_service_account.json'))


@pytest.fixture(autouse=True)
def mock_firebase_and_llm(monkeypatch, tmp_path):
    # Mock firebase_admin credentials and db
    class DummyCred:
        def __init__(self, *args, **kwargs):
            pass

    class DummyRef:
        def __init__(self, path, store):
            self.path = path
            self.store = store

        def get(self):
            return self.store.get(self.path)

        def set(self, value):
            self.store[self.path] = value

        def update(self, updates):
            current = self.store.get(self.path, {})
            current.update(updates)
            self.store[self.path] = current

        def delete(self):
            self.store.pop(self.path, None)

    in_memory_db = {}

    class DummyDB:
        @staticmethod
        def reference(path):
            return DummyRef(path, in_memory_db)

    dummy_service_account = tmp_path / 'dummy_service_account.json'
    dummy_service_account.write_text(json.dumps({"type": "service_account", "project_id": "dummy"}))
    monkeypatch.setenv('FIREBASE_SERVICE_ACCOUNT', str(dummy_service_account))

    # Mock firebase_admin module parts used in app
    from types import ModuleType

    # Build a proper package-like structure for firebase_admin
    mod_firebase_admin = ModuleType('firebase_admin')
    mod_firebase_admin.initialize_app = lambda *args, **kwargs: None

    mod_credentials = ModuleType('firebase_admin.credentials')
    mod_credentials.Certificate = lambda path: DummyCred()

    mod_db = ModuleType('firebase_admin.db')
    mod_db.reference = DummyDB.reference

    # Register in sys.modules and link submodules
    monkeypatch.setitem(os.sys.modules, 'firebase_admin', mod_firebase_admin)
    monkeypatch.setitem(os.sys.modules, 'firebase_admin.credentials', mod_credentials)
    monkeypatch.setitem(os.sys.modules, 'firebase_admin.db', mod_db)
    # Attach attributes so `from firebase_admin import credentials, db` works
    setattr(mod_firebase_admin, 'credentials', mod_credentials)
    setattr(mod_firebase_admin, 'db', mod_db)

    # Mock LLMManager
    class FakeLLM:
        def __init__(self):
            pass

        def generate_response(self, user_prompt: str, system_prompt: str = None, custom_config=None):
            return json.dumps({"test": "response"})

    mod_secure_ai = ModuleType('SecureBYTE_AI')
    mod_secure_ai_main = ModuleType('SecureBYTE_AI.main')
    mod_secure_ai_main.LLMManager = lambda: FakeLLM()
    monkeypatch.setitem(os.sys.modules, 'SecureBYTE_AI', mod_secure_ai)
    monkeypatch.setitem(os.sys.modules, 'SecureBYTE_AI.main', mod_secure_ai_main)
    setattr(mod_secure_ai, 'main', mod_secure_ai_main)

    yield


@pytest.fixture
def client(mock_firebase_and_llm):
    # Import app after mocks are in place
    import sys
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    from app import app
    app.config['TESTING'] = True
    return app.test_client()


def test_get_projects_default_sorting(client):
    """Test default sorting (by updated_at desc)"""
    user_id = 'u1'
    
    # Create three projects with different timestamps
    base_time = datetime.now()
    
    # Project 1 - oldest
    resp1 = client.post(f"/users/{user_id}/projects", json={"project_name": "Project A"})
    assert resp1.status_code == 201
    
    # Project 2 - middle
    resp2 = client.post(f"/users/{user_id}/projects", json={"project_name": "Project B"})
    assert resp2.status_code == 201
    
    # Project 3 - newest
    resp3 = client.post(f"/users/{user_id}/projects", json={"project_name": "Project C"})
    assert resp3.status_code == 201
    
    # Get projects with default sorting
    resp = client.get(f"/users/{user_id}/projects")
    assert resp.status_code == 200
    body = resp.get_json()
    
    assert 'projects' in body
    assert 'sort_by' in body
    assert 'order' in body
    assert body['sort_by'] == 'updated_at'
    assert body['order'] == 'desc'
    assert len(body['projects']) == 3


def test_sort_by_project_name_asc(client):
    """Test sorting by project name in ascending order (A-Z)"""
    user_id = 'u2'
    
    # Create projects with names out of order
    client.post(f"/users/{user_id}/projects", json={"project_name": "Zebra Project"})
    client.post(f"/users/{user_id}/projects", json={"project_name": "Alpha Project"})
    client.post(f"/users/{user_id}/projects", json={"project_name": "Beta Project"})
    
    # Get projects sorted by name ascending
    resp = client.get(f"/users/{user_id}/projects?sort_by=project_name&order=asc")
    assert resp.status_code == 200
    body = resp.get_json()
    
    assert body['sort_by'] == 'project_name'
    assert body['order'] == 'asc'
    projects = body['projects']
    assert len(projects) == 3
    
    # Verify alphabetical order
    assert projects[0]['project_name'] == "Alpha Project"
    assert projects[1]['project_name'] == "Beta Project"
    assert projects[2]['project_name'] == "Zebra Project"


def test_sort_by_project_name_desc(client):
    """Test sorting by project name in descending order (Z-A)"""
    user_id = 'u3'
    
    # Create projects
    client.post(f"/users/{user_id}/projects", json={"project_name": "Alpha Project"})
    client.post(f"/users/{user_id}/projects", json={"project_name": "Zebra Project"})
    client.post(f"/users/{user_id}/projects", json={"project_name": "Beta Project"})
    
    # Get projects sorted by name descending
    resp = client.get(f"/users/{user_id}/projects?sort_by=project_name&order=desc")
    assert resp.status_code == 200
    body = resp.get_json()
    
    assert body['sort_by'] == 'project_name'
    assert body['order'] == 'desc'
    projects = body['projects']
    
    # Verify reverse alphabetical order
    assert projects[0]['project_name'] == "Zebra Project"
    assert projects[1]['project_name'] == "Beta Project"
    assert projects[2]['project_name'] == "Alpha Project"


def test_sort_by_created_at_asc(client):
    """Test sorting by creation date in ascending order (oldest first)"""
    user_id = 'u4'
    
    # Create three projects
    resp1 = client.post(f"/users/{user_id}/projects", json={"project_name": "First"})
    resp2 = client.post(f"/users/{user_id}/projects", json={"project_name": "Second"})
    resp3 = client.post(f"/users/{user_id}/projects", json={"project_name": "Third"})
    
    # Get projects sorted by created_at ascending (oldest first)
    resp = client.get(f"/users/{user_id}/projects?sort_by=created_at&order=asc")
    assert resp.status_code == 200
    body = resp.get_json()
    
    assert body['sort_by'] == 'created_at'
    assert body['order'] == 'asc'
    projects = body['projects']
    
    # First created should be first
    assert projects[0]['project_name'] == "First"
    assert projects[2]['project_name'] == "Third"


def test_sort_by_created_at_desc(client):
    """Test sorting by creation date in descending order (newest first)"""
    user_id = 'u5'
    
    # Create three projects
    resp1 = client.post(f"/users/{user_id}/projects", json={"project_name": "First"})
    resp2 = client.post(f"/users/{user_id}/projects", json={"project_name": "Second"})
    resp3 = client.post(f"/users/{user_id}/projects", json={"project_name": "Third"})
    
    # Get projects sorted by created_at descending (newest first)
    resp = client.get(f"/users/{user_id}/projects?sort_by=created_at&order=desc")
    assert resp.status_code == 200
    body = resp.get_json()
    
    assert body['sort_by'] == 'created_at'
    assert body['order'] == 'desc'
    projects = body['projects']
    
    # Last created should be first
    assert projects[0]['project_name'] == "Third"
    assert projects[2]['project_name'] == "First"


def test_sort_by_updated_at_desc(client):
    """Test sorting by updated_at in descending order"""
    user_id = 'u6'
    
    # Create three projects
    resp1 = client.post(f"/users/{user_id}/projects", json={"project_name": "Project 1"})
    project_id_1 = resp1.get_json()['projectid']
    
    resp2 = client.post(f"/users/{user_id}/projects", json={"project_name": "Project 2"})
    project_id_2 = resp2.get_json()['projectid']
    
    resp3 = client.post(f"/users/{user_id}/projects", json={"project_name": "Project 3"})
    project_id_3 = resp3.get_json()['projectid']
    
    # Update the first project (should become most recent)
    client.put(f"/users/{user_id}/projects/{project_id_1}", 
               json={"project_desc": "Updated description"})
    
    # Get projects sorted by updated_at descending
    resp = client.get(f"/users/{user_id}/projects?sort_by=updated_at&order=desc")
    assert resp.status_code == 200
    body = resp.get_json()
    
    projects = body['projects']
    # Project 1 should be first because it was just updated
    assert projects[0]['project_name'] == "Project 1"


def test_invalid_sort_by_parameter(client):
    """Test that invalid sort_by parameter returns error"""
    user_id = 'u7'
    
    # Create a project
    client.post(f"/users/{user_id}/projects", json={"project_name": "Test"})
    
    # Try to sort by invalid field
    resp = client.get(f"/users/{user_id}/projects?sort_by=invalid_field")
    assert resp.status_code == 400
    body = resp.get_json()
    assert 'error' in body
    assert 'Invalid sort_by parameter' in body['error']


def test_invalid_order_parameter(client):
    """Test that invalid order parameter returns error"""
    user_id = 'u8'
    
    # Create a project
    client.post(f"/users/{user_id}/projects", json={"project_name": "Test"})
    
    # Try to use invalid order
    resp = client.get(f"/users/{user_id}/projects?sort_by=project_name&order=invalid")
    assert resp.status_code == 400
    body = resp.get_json()
    assert 'error' in body
    assert 'Invalid order parameter' in body['error']


def test_empty_project_list_sorting(client):
    """Test sorting works correctly when user has no projects"""
    user_id = 'u9'
    
    # Get projects for user with no projects
    resp = client.get(f"/users/{user_id}/projects?sort_by=project_name&order=asc")
    assert resp.status_code == 200
    body = resp.get_json()
    
    assert body['projects'] == []
    assert body['total'] == 0
    assert body['sort_by'] == 'project_name'
    assert body['order'] == 'asc'


def test_case_insensitive_name_sorting(client):
    """Test that project name sorting is case-insensitive"""
    user_id = 'u10'
    
    # Create projects with mixed case names
    client.post(f"/users/{user_id}/projects", json={"project_name": "apple"})
    client.post(f"/users/{user_id}/projects", json={"project_name": "Banana"})
    client.post(f"/users/{user_id}/projects", json={"project_name": "CHERRY"})
    
    # Get projects sorted by name ascending
    resp = client.get(f"/users/{user_id}/projects?sort_by=project_name&order=asc")
    assert resp.status_code == 200
    body = resp.get_json()
    
    projects = body['projects']
    # Should be sorted case-insensitively
    assert projects[0]['project_name'] == "apple"
    assert projects[1]['project_name'] == "Banana"
    assert projects[2]['project_name'] == "CHERRY"