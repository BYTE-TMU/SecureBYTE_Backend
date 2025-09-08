import json
import os
import builtins
import types

import pytest


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
    import types as _types
    import types
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

    # Mock LLMManager in backend app import path to return deterministic JSON
    class FakeLLM:
        def __init__(self):
            pass

        def generate_response(self, user_prompt: str, system_prompt: str = None, custom_config=None):
            # Return valid JSON depending on prompt content
            # Minimal valid structures for both logic and testing
            if 'Logic' in user_prompt or 'logic' in user_prompt:
                return json.dumps({
                    "review_time": "2025-01-01T00:00:00Z",
                    "files": [
                        {"logic Errors": [{"function": "foo", "feedback": "Potential issue"}]}
                    ]
                })
            else:
                return json.dumps({
                    "review_time": "2025-01-01T00:00:00Z",
                    "files": [
                        {
                            "code_content": "def foo():\n    return 1",
                            "test_cases": [
                                {
                                    "id": "TC001",
                                    "description": "basic",
                                    "input": [],
                                    "expected_output": 1,
                                    "test_type": "positive",
                                    "notes": ""
                                }
                            ]
                        }
                    ]
                })

    # Mock SecureBYTE_AI.main as a real module with LLMManager
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


def _project_ref_path(user_id, project_id):
    return f'users/{user_id}/projects/{project_id}'


def _submission_ref_path(user_id, submission_id):
    return f'users/{user_id}/submissions/{submission_id}'


def test_logic_review_happy_path(client):
    user_id = 'u1'
    # Create project
    resp = client.post(f"/users/{user_id}/projects", json={"project_name": "p1"})
    assert resp.status_code == 201
    project_id = resp.get_json()["projectid"]

    # Create submission
    resp = client.post(
        f"/users/{user_id}/projects/{project_id}/submissions",
        json={"filename": "file.py", "code": "def foo():\n    return 1"},
    )
    assert resp.status_code == 201
    submission_id = resp.get_json()["id"]

    # Call logic review
    resp = client.post(
        f"/users/{user_id}/submissions/{submission_id}/logic-review",
        json={"code": "def foo():\n    return 1"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["review_type"] == "logic"
    assert body["submission_id"] == submission_id
    assert isinstance(body["response"], dict)


def test_testing_review_happy_path(client):
    user_id = 'u2'
    # Create project
    resp = client.post(f"/users/{user_id}/projects", json={"project_name": "p2"})
    assert resp.status_code == 201
    project_id = resp.get_json()["projectid"]

    # Create submission
    resp = client.post(
        f"/users/{user_id}/projects/{project_id}/submissions",
        json={"filename": "file.py", "code": "def foo():\n    return 1"},
    )
    assert resp.status_code == 201
    submission_id = resp.get_json()["id"]

    # Call testing review
    resp = client.post(
        f"/users/{user_id}/submissions/{submission_id}/testing-review",
        json={"code": "def foo():\n    return 1"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["review_type"] == "testing"
    assert body["submission_id"] == submission_id
    assert isinstance(body["response"], dict)


