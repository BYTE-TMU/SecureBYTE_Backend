"""
Test script for Memory Service
Run this to verify ChromaDB integration is working
"""

import sys
import os
import shutil

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from services.memory_service import MemoryService
from datetime import datetime
import json

def test_memory_service():
    """Test all memory service functionality"""
    
    print("="*60)
    print("Testing SecureBYTE Memory Service")
    print("="*60)
    
    # Initialize
    print("\n1. Initializing Memory Service (PersistentClient)...")
    try:
        memory = MemoryService(persist_directory="./test_chroma_db")
        print("✓ Memory service initialized successfully")
        print("✓ Using PersistentClient - data will persist to disk")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        return
    
    # Test storage
    print("\n2. Testing Code Submission Storage...")
    try:
        memory.store_code_submission(
            user_id="test_user_123",
            submission_id="sub_001",
            project_id="proj_001",
            filename="example.py",
            code="""
def authenticate_user(username, password):
    # Insecure: SQL injection vulnerability
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    return db.execute(query)
            """,
            language="python"
        )
        print("✓ Code submission stored")
    except Exception as e:
        print(f"✗ Failed to store code: {e}")
    
    # Test security review storage
    print("\n3. Testing Security Review Storage...")
    try:
        security_review = {
            "review_time": datetime.now().isoformat(),
            "files": [
                {
                    "filename": "example.py",
                    "issues": [
                        {
                            "line": 3,
                            "feedback": "SQL injection vulnerability: User input directly concatenated into query",
                            "severity": {
                                "level": "critical",
                                "score": 5
                            }
                        }
                    ]
                }
            ]
        }
        memory.store_security_review(
            user_id="test_user_123",
            project_id="proj_001",
            review_data=security_review
        )
        print("✓ Security review stored")
    except Exception as e:
        print(f"✗ Failed to store review: {e}")
    
    # Test logic review storage
    print("\n4. Testing Logic Review Storage...")
    try:
        logic_review = {
            "review_time": datetime.now().isoformat(),
            "files": [
                {
                    "logic Errors": [
                        {
                            "function": "authenticate_user",
                            "feedback": "No error handling for database connection failures"
                        }
                    ]
                }
            ]
        }
        memory.store_logic_review(
            user_id="test_user_123",
            submission_id="sub_001",
            project_id="proj_001",
            review_data=logic_review
        )
        print("✓ Logic review stored")
    except Exception as e:
        print(f"✗ Failed to store logic review: {e}")
    
    # Test similar code search
    print("\n5. Testing Similar Code Search...")
    try:
        similar_code = memory.get_similar_code(
            code_snippet="SELECT * FROM users WHERE",
            user_id="test_user_123",
            n_results=3
        )
        print(f"✓ Found {len(similar_code)} similar code items")
        if similar_code:
            print(f"  - Most similar: {similar_code[0]['metadata']['filename']}")
            print(f"  - Distance: {similar_code[0]['distance']:.3f}")
    except Exception as e:
        print(f"✗ Failed to search similar code: {e}")
    
    # Test similar security issues
    print("\n6. Testing Similar Security Issues Search...")
    try:
        similar_issues = memory.get_similar_security_issues(
            issue_description="SQL injection",
            user_id="test_user_123",
            n_results=3
        )
        print(f"✓ Found {len(similar_issues)} similar security issues")
        if similar_issues:
            issue = similar_issues[0]
            print(f"  - Severity: {issue['metadata']['severity']}")
            print(f"  - File: {issue['metadata']['filename']}")
    except Exception as e:
        print(f"✗ Failed to search similar issues: {e}")
    
    # Test project context
    print("\n7. Testing Project Context Storage...")
    try:
        memory.store_project_context(
            user_id="test_user_123",
            project_id="proj_001",
            project_name="Test Security App",
            project_desc="A sample application for testing security reviews",
            file_structure=["example.py", "utils.py", "models.py"]
        )
        print("✓ Project context stored")
    except Exception as e:
        print(f"✗ Failed to store project context: {e}")
    
    # Test enhanced context retrieval
    print("\n8. Testing Enhanced Context Retrieval...")
    try:
        enhanced_context = memory.get_enhanced_context(
            user_id="test_user_123",
            project_id="proj_001",
            current_code="query = 'SELECT * FROM users WHERE id=' + user_id",
            review_type="security"
        )
        print("✓ Enhanced context retrieved")
        print(f"  - Similar code items: {len(enhanced_context.get('similar_code', []))}")
        print(f"  - Past issues: {len(enhanced_context.get('past_issues', []))}")
        print(f"  - Has project context: {enhanced_context.get('project_context') is not None}")
    except Exception as e:
        print(f"✗ Failed to get enhanced context: {e}")
    
    # Test user interaction storage
    print("\n9. Testing User Interaction Storage...")
    try:
        memory.store_user_interaction(
            user_id="test_user_123",
            interaction_type="preference",
            context="User prefers detailed security explanations with code examples",
            metadata={"preference_type": "review_detail"}
        )
        print("✓ User interaction stored")
    except Exception as e:
        print(f"✗ Failed to store user interaction: {e}")
    
    # Get statistics
    print("\n10. Getting Collection Statistics...")
    try:
        stats = memory.get_collection_stats()
        print("✓ Collection statistics:")
        for collection, count in stats.items():
            print(f"  - {collection}: {count} items")
    except Exception as e:
        print(f"✗ Failed to get stats: {e}")
    
    # Test data cleanup
    print("\n11. Testing Data Cleanup (GDPR)...")
    try:
        memory.clear_user_data("test_user_123")
        print("✓ User data cleared")
        
        # Verify deletion
        stats_after = memory.get_collection_stats()
        print("  Statistics after cleanup:")
        for collection, count in stats_after.items():
            print(f"  - {collection}: {count} items")
    except Exception as e:
        print(f"✗ Failed to clear data: {e}")
    
    print("\n" + "="*60)
    print("Memory Service Test Complete!")
    print("="*60)
    print("\nNext steps:")
    print("1. If all tests passed, integrate into app.py")
    print("2. Install dependencies: pip install -r requirements.txt")
    print("3. Follow MEMORY_IMPLEMENTATION_GUIDE.md for integration")
    print("\nCleanup:")
    print("- Test database created at: ./test_chroma_db")
    print("- You can delete this directory after testing")

    # --- Auto-cleanup: remove the test Chroma DB directory created by this test ---
    print("\n12. Cleaning up test database directory...")
    # The test database path is created relative to the repository backend folder.
    test_db_dir = os.path.join(parent_dir, "test_chroma_db")
    try:
        if os.path.exists(test_db_dir):
            shutil.rmtree(test_db_dir)
            print(f"✓ Removed test database at: {test_db_dir}")
        else:
            print(f"✓ No test database found at: {test_db_dir}")
    except Exception as e:
        print(f"✗ Failed to remove test database: {e}")

if __name__ == "__main__":
    test_memory_service()
