# Memory Service - Complete Guide

## Overview

The Memory Service is a ChromaDB-based vector database system that enhances AI code reviews by providing historical context. It stores embeddings of code submissions, review findings, and project metadata, enabling the AI to recognize patterns, identify recurring issues, and provide more consistent, context-aware feedback.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [How It Works](#how-it-works)
5. [Integration Guide](#integration-guide)
6. [API Reference](#api-reference)
7. [Data Storage](#data-storage)
8. [Usage Examples](#usage-examples)

---

## What It Does

### Before Memory Service
```
User → Submit Code → LLM Review → Response
```

### With Memory Service
```
User → Submit Code → 
    ↓
Query Memory (similar code, past issues, project context) → 
    ↓
Enhanced LLM Prompt with Historical Context →
    ↓
LLM Review (with awareness of past patterns) →
    ↓
Store in Memory (for future reviews) →
    ↓
Response to User
```

### Key Benefits

1. **Pattern Recognition**: AI remembers similar issues from previous reviews
2. **Consistency**: Same standards applied across all reviews in a project
3. **Learning**: System improves as it processes more code
4. **Context-Aware**: Understands project structure and coding patterns
5. **Persistent**: Data survives server restarts automatically

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    Flask Backend                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌────────────────┐         ┌─────────────────┐        │
│  │  Review        │ ◄─────► │  Memory Service │        │
│  │  Endpoints     │         │  (ChromaDB)     │        │
│  └────────────────┘         └─────────────────┘        │
│         │                            │                  │
│         ▼                            ▼                  │
│  ┌────────────────┐         ┌─────────────────┐        │
│  │  LLM Manager   │         │  Vector Storage │        │
│  │  (AI Module)   │         │  (./chroma_db/) │        │
│  └────────────────┘         └─────────────────┘        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Data Collections (5 Total)

| Collection | Stores | Used For |
|-----------|---------|----------|
| `code_submissions` | Code with embeddings | Finding similar code patterns |
| `security_reviews` | Security findings | Identifying recurring security issues |
| `logic_reviews` | Logic/testing errors | Recognizing similar logic problems |
| `user_context` | User preferences | Personalizing reviews |
| `project_context` | Project metadata | Understanding project structure |

---

## Installation

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

This installs:
- `chromadb>=0.4.22` - Vector database
- `sentence-transformers>=2.2.0` - Free local embeddings
- `openai>=1.0.0` - OpenAI embeddings (optional, better quality)

### 2. (Optional) Configure OpenAI Embeddings

For higher quality embeddings (recommended but costs money):

```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

If not set, the system uses free local Sentence Transformers (still works great).

### 3. Verify Installation

```bash
python -c "import chromadb; print('✓ ChromaDB installed')"
python -c "from memory_service import MemoryService; print('✓ Memory service available')"
```

---

## How It Works

### Review Flow with Memory

```
Step 1: User Submits Code for Review
   │
   ▼
Step 2: System Queries Memory
   │  • Find similar code from past submissions
   │  • Retrieve related issues from previous reviews
   │  • Get project context and structure
   │
   ▼
Step 3: Build Enhanced Prompt
   │  • Original prompt template
   │  + Historical context from memory
   │  + Current code to review
   │
   ▼
Step 4: LLM Generates Review
   │  • Has full historical context
   │  • Can identify patterns
   │  • Provides consistent feedback
   │
   ▼
Step 5: Store Results in Memory
   │  • Save review findings
   │  • Store code submission
   │  • Update project context
   │
   ▼
Step 6: Return Response to User
```

### Memory Query Process

When you submit code like:
```python
SELECT * FROM users WHERE id = ?
```

The system:
1. **Converts to vector** (embedding): `[0.234, -0.891, 0.456, ...]`
2. **Searches ChromaDB** for similar vectors
3. **Returns matches** with metadata:
   - Similar code from `auth.py` (87% similarity)
   - SQL injection found in similar code previously
   - Project uses parameterized queries elsewhere
4. **Enhances prompt** with this context
5. **LLM reviews** with awareness of past patterns

---

## Integration Guide

### Step 1: Import Memory Service

Add to `app.py` at the top:

```python
from memory_service import MemoryService
```

### Step 2: Initialize Memory Service

Add after LLM initialization (around line 100):

```python
# Initialize Memory Service
memory_service = None
try:
    memory_service = MemoryService(persist_directory="./chroma_db")
    print("✓ Memory service initialized successfully (PersistentClient)")
    print("✓ Data will persist across server restarts")
    stats = memory_service.get_collection_stats()
    print(f"Memory stats: {stats}")
except Exception as e:
    print(f"Warning: Could not initialize memory service: {e}")
    memory_service = None
```

### Step 3: Update Review Function

Replace `handle_llm_review()` function (around line 650):

```python
def handle_llm_review(review_type, user_id, project_or_submission_id, data):
    """Handle LLM review requests with memory context"""
    
    # Extract code and prepare
    code = data.get('code', '')
    compressed_code = compress_code(code)
    
    # Get IDs for memory storage
    if review_type == "security":
        project_id = project_or_submission_id
        submission_id = None
    else:
        submission_id = project_or_submission_id
        # Get project_id from submission
        submission_ref = db.reference(f'users/{user_id}/submissions/{submission_id}')
        submission_data = submission_ref.get()
        project_id = submission_data.get('projectid') if submission_data else None
    
    # ===== QUERY MEMORY FOR CONTEXT =====
    context_prompt = ""
    if memory_service and project_id:
        try:
            context = memory_service.get_enhanced_context(
                user_id=user_id,
                project_id=project_id,
                code_snippet=compressed_code,
                review_type=review_type
            )
            
            if context["similar_code"] or context["past_issues"]:
                context_prompt = "\n\n" + "=" * 60 + "\n"
                context_prompt += "## HISTORICAL CONTEXT FROM PREVIOUS REVIEWS\n"
                context_prompt += "(Use this to identify patterns and recurring issues)\n"
                context_prompt += "=" * 60 + "\n\n"
                
                # Add similar code
                if context["similar_code"]:
                    context_prompt += "## Previously Reviewed Similar Code:\n"
                    for i, item in enumerate(context["similar_code"], 1):
                        filename = item['metadata'].get('filename', 'unknown')
                        similarity = (1 - item['distance']) * 100
                        context_prompt += f"{i}. File: {filename} (similarity: {similarity:.0f}%)\n"
                    context_prompt += "\n"
                
                # Add past issues
                if context["past_issues"]:
                    context_prompt += "## Similar Issues Found Previously:\n"
                    for i, item in enumerate(context["past_issues"], 1):
                        doc = item['document']
                        context_prompt += f"{i}. {doc}\n"
                    context_prompt += "\n"
                
                # Add project context
                if context["project_context"]:
                    proj_ctx = context["project_context"]
                    proj_name = proj_ctx.get('project_name', 'Unknown')
                    file_count = proj_ctx.get('file_count', 0)
                    context_prompt += f"## Project: {proj_name} ({file_count} files)\n"
                
                context_prompt += "=" * 60 + "\n\n"
        except Exception as e:
            print(f"Warning: Could not get memory context: {e}")
    
    # Load prompt template
    prompt_file = f"prompts/{review_type}_prompt.txt"
    with open(prompt_file, 'r') as f:
        prompt_template = f.read()
    
    # Build enhanced prompt
    enhanced_prompt = prompt_template + context_prompt + f"\n\nCode to review:\n{compressed_code}"
    
    # Call LLM
    response = llm.generate_response(enhanced_prompt)
    
    # ===== STORE RESULTS IN MEMORY =====
    if memory_service and response:
        try:
            # Store the review
            if review_type == "security":
                memory_service.store_security_review(
                    user_id=user_id,
                    project_id=project_id,
                    review_data=response
                )
                print("✓ Stored security review in memory")
            else:
                memory_service.store_logic_review(
                    user_id=user_id,
                    submission_id=submission_id,
                    project_id=project_id,
                    review_data=response
                )
                print("✓ Stored logic review in memory")
            
            # Store the code submission
            if submission_id:
                memory_service.store_code_submission(
                    user_id=user_id,
                    submission_id=submission_id,
                    project_id=project_id,
                    filename=data.get('filename', 'unknown'),
                    code=compressed_code,
                    language=data.get('language', 'unknown')
                )
                print("✓ Stored code submission in memory")
        except Exception as e:
            print(f"Warning: Could not store in memory: {e}")
    
    return {
        "success": True,
        "review_type": review_type,
        "response": response
    }
```

### Step 4: Add Memory Endpoints

Add before `if __name__ == '__main__':` (around line 900):

```python
# ==================== MEMORY ENDPOINTS ====================

@app.route('/users/<user_id>/memory/stats', methods=['GET'])
def get_memory_stats(user_id):
    """Get memory statistics for a user"""
    if not memory_service:
        return jsonify({"error": "Memory service not available"}), 503
    
    try:
        stats = memory_service.get_collection_stats()
        user_stats = memory_service.get_user_stats(user_id)
        
        return jsonify({
            "success": True,
            "global_stats": stats,
            "user_stats": user_stats,
            "user_id": user_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/users/<user_id>/memory/similar-code', methods=['POST'])
def find_similar_code(user_id):
    """Find similar code from memory"""
    if not memory_service:
        return jsonify({"error": "Memory service not available"}), 503
    
    try:
        data = request.get_json()
        code = data.get('code')
        project_id = data.get('project_id')
        n_results = data.get('n_results', 5)
        
        if not code:
            return jsonify({"error": "code is required"}), 400
        
        results = memory_service.get_similar_code(
            code_snippet=code,
            user_id=user_id,
            project_id=project_id,
            n_results=n_results
        )
        
        return jsonify({
            "success": True,
            "results": results,
            "count": len(results)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/users/<user_id>/memory/clear', methods=['DELETE'])
def clear_user_memory(user_id):
    """Clear all memory for a user (GDPR compliance)"""
    if not memory_service:
        return jsonify({"error": "Memory service not available"}), 503
    
    try:
        data = request.get_json() or {}
        confirm = data.get('confirm', False)
        
        if not confirm:
            return jsonify({
                "error": "Must set 'confirm': true to clear data"
            }), 400
        
        deleted = memory_service.clear_user_data(user_id)
        
        return jsonify({
            "success": True,
            "message": f"Cleared all data for user {user_id}",
            "deleted_count": deleted,
            "user_id": user_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

---

## API Reference

### Memory Endpoints

#### GET `/users/<user_id>/memory/stats`
Get memory statistics for a user.

**Response:**
```json
{
  "success": true,
  "global_stats": {
    "code_submissions": 150,
    "security_reviews": 45,
    "logic_reviews": 89,
    "user_context": 12,
    "project_context": 8
  },
  "user_stats": {
    "code_submissions": 25,
    "security_reviews": 8,
    "logic_reviews": 15
  }
}
```

#### POST `/users/<user_id>/memory/similar-code`
Find similar code from memory.

**Request:**
```json
{
  "code": "SELECT * FROM users WHERE id = ?",
  "project_id": "proj123",
  "n_results": 5
}
```

**Response:**
```json
{
  "success": true,
  "results": [
    {
      "document": "File: auth.py\nCode: SELECT * FROM users...",
      "metadata": {
        "filename": "auth.py",
        "user_id": "user123",
        "similarity": 87
      },
      "distance": 0.13
    }
  ],
  "count": 5
}
```

#### DELETE `/users/<user_id>/memory/clear`
Clear all memory data for a user (GDPR compliance).

**Request:**
```json
{
  "confirm": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Cleared all data for user user123",
  "deleted_count": 45
}
```

### Memory Service Methods

These are called internally by the Flask app:

```python
# Query methods
memory_service.get_similar_code(code_snippet, user_id, project_id, n_results)
memory_service.get_similar_issues(issue_text, user_id, review_type, n_results)
memory_service.get_enhanced_context(user_id, project_id, code_snippet, review_type)

# Storage methods
memory_service.store_code_submission(user_id, submission_id, project_id, filename, code, language)
memory_service.store_security_review(user_id, project_id, review_data)
memory_service.store_logic_review(user_id, submission_id, project_id, review_data)

# Stats & management
memory_service.get_collection_stats()
memory_service.get_user_stats(user_id)
memory_service.clear_user_data(user_id)
```

---

## Data Storage

### Storage Location

All data is stored locally in:
```
./chroma_db/
├── chroma.sqlite3              # Metadata database
├── [collection-uuid]/
│   ├── data_level0.bin        # Vector embeddings
│   ├── header.bin             # Collection metadata
│   └── link_lists.bin         # Index structure
└── ...
```

### Persistent Storage

The system uses **ChromaDB PersistentClient** which provides:

✅ **Automatic persistence** - Every operation saves to disk immediately
✅ **Survives restarts** - Data loads automatically when server starts
✅ **Thread-safe** - Multiple concurrent operations are safe
✅ **No manual saves** - No need to call save() or persist()
✅ **Crash recovery** - Data is safe after operation completes

### Storage Size Estimates

| Data Type | Size per Item | 10,000 Items |
|-----------|---------------|--------------|
| Code submission (100 lines) | ~2 KB | 20 MB |
| Security issue | ~500 bytes | 5 MB |
| Logic error | ~500 bytes | 5 MB |
| Embedding (384 dim) | ~1.5 KB | 15 MB |
| **Total** | | **~50-100 MB** |

### Backup & Restore

**Backup:**
```bash
# Stop the server first (recommended)
tar -czf chroma_backup_$(date +%Y%m%d).tar.gz ./chroma_db/
```

**Restore:**
```bash
# Stop the server
tar -xzf chroma_backup_20251110.tar.gz
# Start the server - data restored automatically
```

---

## Usage Examples

### Starting the Server

```bash
cd backend
python app.py
```

Expected output:
```
✓ LLM Manager initialized successfully
✓ Memory service initialized successfully (PersistentClient)
✓ Data will persist across server restarts
Memory stats: {'code_submissions': 0, 'security_reviews': 0, ...}
* Running on http://127.0.0.1:5000
```

### Submitting a Review

```bash
# Logic review
curl -X POST http://localhost:5000/users/user123/submissions/sub456/logic_review \
  -H "Content-Type: application/json" \
  -d '{
    "code": "function factorial(n) { return n * factorial(n-1); }",
    "filename": "math.js",
    "language": "javascript"
  }'
```

### Checking Memory Stats

```bash
curl http://localhost:5000/users/user123/memory/stats
```

### Finding Similar Code

```bash
curl -X POST http://localhost:5000/users/user123/memory/similar-code \
  -H "Content-Type: application/json" \
  -d '{
    "code": "SELECT * FROM users WHERE username = ?",
    "project_id": "proj789",
    "n_results": 3
  }'
```

### Clearing User Data (GDPR)

```bash
curl -X DELETE http://localhost:5000/users/user123/memory/clear \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

---

## Example Enhanced Prompt

When you submit code for review, the LLM receives a prompt like this:

```
[Original Security Prompt Template]

============================================================
## HISTORICAL CONTEXT FROM PREVIOUS REVIEWS
(Use this to identify patterns and recurring issues)
============================================================

## Previously Reviewed Similar Code:
1. File: auth.py (similarity: 87%)
2. File: login.js (similarity: 76%)
3. File: database.py (similarity: 65%)

## Similar Issues Found Previously:
1. critical - SQL injection vulnerability in line 42
   Issue: User input directly concatenated into query
   
2. high - Missing input validation on username field
   Issue: No length or character validation before query

3. medium - Insufficient error handling
   Issue: Database errors expose internal structure

## Project: User Auth System (23 files)
============================================================

Code to review:
[Your submitted code here]
```

This gives the AI full context about:
- Similar code you've written before
- Issues found in similar contexts
- Overall project structure

Result: More accurate, consistent, and context-aware reviews! 🎯

---

## Troubleshooting

### Memory Service Won't Initialize

**Problem:** Server starts but memory service fails to initialize

**Solution:**
```bash
# Check ChromaDB is installed
pip install chromadb>=0.4.22

# Check directory permissions
mkdir -p ./chroma_db
chmod 755 ./chroma_db

# Check for conflicts
rm -rf ./chroma_db
# Restart server
```

### No Historical Context in Reviews

**Problem:** Reviews work but don't include historical context

**Solution:**
1. Check memory service initialized successfully in logs
2. Verify data is being stored: `curl .../memory/stats`
3. Check `memory_service` variable is not `None` in `handle_llm_review()`
4. Submit a few reviews to build up context

### Data Not Persisting

**Problem:** Memory stats show 0 after server restart

**Solution:**
1. Verify using PersistentClient (not ephemeral Client)
2. Check `./chroma_db/` directory exists and has files
3. Check file permissions on the directory
4. Check logs for write errors during storage

### Performance Issues

**Problem:** Reviews are slow with memory enabled

**Solution:**
1. Use SSD for `./chroma_db/` directory
2. Reduce `n_results` in similarity searches (default 3-5)
3. Consider using OpenAI embeddings (faster than local)
4. Index grows large: consider pruning old data

---

## Summary

The Memory Service transforms your code review system from stateless to stateful, enabling the AI to:

- 🧠 **Remember** previous code and issues
- 🔍 **Recognize** patterns across reviews
- 📊 **Provide** consistent feedback
- 🎯 **Improve** over time with more data
- 💾 **Persist** all data automatically

**Integration is simple**: Add 3 code blocks to `app.py`, and the memory system handles the rest automatically.

**Zero maintenance**: Data persists automatically, no manual saves needed, crash-safe storage.

**Privacy-friendly**: Supports GDPR compliance with user data deletion endpoint.

---

For visual architecture diagrams, see `ARCHITECTURE_DIAGRAMS.md`.
