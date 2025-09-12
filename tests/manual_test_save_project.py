import os
import sys
import json
import types
from copy import deepcopy


# -------------------- Mock firebase_admin --------------------
STORE = {}


def _walk_to_parent(path_parts):
    node = STORE
    for part in path_parts[:-1]:
        node = node.setdefault(part, {})
    return node, path_parts[-1]


class MockDBRef:
    def __init__(self, path: str):
        # Normalize and split path like 'users/<user>/projects/<project>'
        normalized = path.strip("/")
        self.parts = [p for p in normalized.split("/") if p]

    def get(self):
        node = STORE
        for part in self.parts:
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        # Return a deep copy to mimic DB behavior
        return deepcopy(node)

    def set(self, data):
        parent, key = _walk_to_parent(self.parts)
        parent[key] = deepcopy(data)

    def update(self, data):
        parent, key = _walk_to_parent(self.parts)
        if key not in parent or not isinstance(parent.get(key), dict):
            parent[key] = {}
        target = parent[key]
        target.update(deepcopy(data))

    def delete(self):
        parent, key = _walk_to_parent(self.parts)
        if key in parent:
            del parent[key]


def mock_reference(path: str):
    return MockDBRef(path)


class MockCredentialsNS:
    class Certificate:
        def __init__(self, path):
            self.path = path


class MockFirebaseAdmin(types.ModuleType):
    def __init__(self):
        super().__init__("firebase_admin")
        self.credentials = MockCredentialsNS
        self.db = types.SimpleNamespace(reference=mock_reference)

    def initialize_app(self, *_args, **_kwargs):
        # No-op
        return None


# Inject mock before importing the app
sys.modules["firebase_admin"] = MockFirebaseAdmin()


# Ensure FIREBASE_SERVICE_ACCOUNT is set so app doesn't raise
os.environ.setdefault("FIREBASE_SERVICE_ACCOUNT", "/tmp/mock-firebase.json")


# Import the Flask app
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app as backend  # noqa: E402


def create_project(client, user_id: str, name: str):
    resp = client.post(f"/users/{user_id}/projects", json={"project_name": name})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["projectid"]


def create_submission(client, user_id: str, project_id: str, filename: str, code: str):
    resp = client.post(
        f"/users/{user_id}/projects/{project_id}/submissions",
        json={"filename": filename, "code": code},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["id"]


def get_submission(client, user_id: str, submission_id: str):
    resp = client.get(f"/users/{user_id}/submissions/{submission_id}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def run_tests():
    user_id = "tester-save"
    with backend.app.test_client() as client:
        # Create project and submissions
        project_id = create_project(client, user_id, "save-endpoint-demo")
        sub_a = create_submission(client, user_id, project_id, "a.py", "print(1)")
        sub_b = create_submission(client, user_id, project_id, "b.py", "print(10)")

        # Test 1: Successful save of multiple files
        payload_ok = [
            {"fileid": sub_a, "filename": "a.py", "code": "print(2)"},
            {"fileid": sub_b, "filename": "b.py", "code": "x=1"},
        ]
        r1 = client.put(
            f"/users/{user_id}/projects/{project_id}/save",
            json=payload_ok,
        )
        print("TEST1 status:", r1.status_code)
        print("TEST1 resp:", r1.get_json())
        assert r1.status_code == 200, r1.get_data(as_text=True)

        sub_a_obj = get_submission(client, user_id, sub_a)
        sub_b_obj = get_submission(client, user_id, sub_b)
        print("TEST1 a.py code:", sub_a_obj.get("code"))
        print("TEST1 b.py code:", sub_b_obj.get("code"))
        assert sub_a_obj.get("code") == "print(2)"
        assert sub_b_obj.get("code") == "x=1"

        # Test 2: Partial failure (first item invalid) — current behavior may early return
        payload_partial = [
            {"fileid": "nonexistent", "filename": "ghost.py", "code": "noop"},
            {"fileid": sub_a, "filename": "a.py", "code": "print(3)"},
        ]
        r2 = client.put(
            f"/users/{user_id}/projects/{project_id}/save",
            json=payload_partial,
        )
        print("TEST2 status:", r2.status_code)
        print("TEST2 resp:", r2.get_json())
        assert r2.status_code == 400, "Expected 400 for partial failure"

        # Confirm that valid item may not be updated due to early return behavior
        sub_a_after = get_submission(client, user_id, sub_a)
        print("TEST2 a.py code (should still be print(2)):", sub_a_after.get("code"))
        assert sub_a_after.get("code") == "print(2)", "save likely returned early"

    print("All save_project tests completed.")


if __name__ == "__main__":
    run_tests()


