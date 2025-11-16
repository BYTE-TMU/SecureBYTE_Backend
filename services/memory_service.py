"""
Context Memory Service using ChromaDB
Manages vector embeddings for code reviews, submissions, and user context
"""

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import hashlib

load_dotenv()

class MemoryService:
    """
    Manages context memory using ChromaDB for semantic search and retrieval
    """
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        """
        Initialize ChromaDB client and collections
        
        Args:
            persist_directory: Directory to persist ChromaDB data
        """
        self.persist_directory = persist_directory
        
        # Create directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB client with persistent storage
        # Use PersistentClient for local persistent storage
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Use OpenAI embeddings (you can switch to sentence-transformers for free option)
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if openai_api_key:
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=openai_api_key,
                model_name="text-embedding-3-small"  # Cheaper and faster
            )
        else:
            # Fallback to free sentence transformers
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
        
        # Create collections for different types of memory
        self._initialize_collections()
    
    def _initialize_collections(self):
        """Initialize different ChromaDB collections"""
        
        # Collection for code submissions and their context
        self.code_collection = self.client.get_or_create_collection(
            name="code_submissions",
            embedding_function=self.embedding_function,
            metadata={"description": "Code submissions with file context"}
        )
        
        # Collection for security review findings
        self.security_collection = self.client.get_or_create_collection(
            name="security_reviews",
            embedding_function=self.embedding_function,
            metadata={"description": "Security review findings and patterns"}
        )
        
        # Collection for logic review findings
        self.logic_collection = self.client.get_or_create_collection(
            name="logic_reviews",
            embedding_function=self.embedding_function,
            metadata={"description": "Logic errors and patterns"}
        )
        
        # Collection for user interactions and preferences
        self.user_collection = self.client.get_or_create_collection(
            name="user_context",
            embedding_function=self.embedding_function,
            metadata={"description": "User preferences and interaction history"}
        )
        
        # Collection for project-level context
        self.project_collection = self.client.get_or_create_collection(
            name="project_context",
            embedding_function=self.embedding_function,
            metadata={"description": "Project structure and relationships"}
        )
    
    def _generate_id(self, *components) -> str:
        """Generate a unique ID from components"""
        combined = "_".join(str(c) for c in components)
        return hashlib.md5(combined.encode()).hexdigest()
        
    def store_code_submission(self, 
                             user_id: str, 
                             submission_id: str,
                             project_id: str,
                             filename: str,
                             code: str,
                             language: Optional[str] = None):
        """
        Store a code submission in vector memory
        
        Args:
            user_id: User ID
            submission_id: Submission ID
            project_id: Project ID
            filename: File name
            code: Source code
            language: Programming language (optional)
        """
        doc_id = self._generate_id(user_id, submission_id)
        
        # Create a rich context document
        document = f"""
        File: {filename}
        Language: {language or 'unknown'}
        Code:
        {code}
        """
        
        metadata = {
            "user_id": user_id,
            "submission_id": submission_id,
            "project_id": project_id,
            "filename": filename,
            "language": language or "unknown",
            "timestamp": datetime.now().isoformat(),
            "type": "code_submission"
        }
        
        self.code_collection.add(
            documents=[document],
            metadatas=[metadata],
            ids=[doc_id]
        )
    
    def get_similar_code(self, 
                        code_snippet: str,
                        user_id: Optional[str] = None,
                        project_id: Optional[str] = None,
                        n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Find similar code submissions
        
        Args:
            code_snippet: Code to search for
            user_id: Filter by user (optional)
            project_id: Filter by project (optional)
            n_results: Number of results to return
            
        Returns:
            List of similar code submissions with metadata
        """
        where_filter = {"type": "code_submission"}
        if user_id:
            where_filter["user_id"] = user_id
        if project_id:
            where_filter["project_id"] = project_id
        
        results = self.code_collection.query(
            query_texts=[code_snippet],
            where=where_filter if where_filter else None,
            n_results=n_results
        )
        
        return self._format_results(results)
        
    def store_security_review(self,
                             user_id: str,
                             project_id: str,
                             review_data: Dict[str, Any]):
        """
        Store security review findings
        
        Args:
            user_id: User ID
            project_id: Project ID
            review_data: Security review JSON data
        """
        review_id = self._generate_id(user_id, project_id, datetime.now().isoformat())
        
        # Extract issues and create searchable documents
        files = review_data.get('files', [])
        for file_idx, file_data in enumerate(files):
            filename = file_data.get('filename', 'unknown')
            issues = file_data.get('issues', [])
            
            for issue_idx, issue in enumerate(issues):
                issue_id = f"{review_id}_file{file_idx}_issue{issue_idx}"
                
                # Create rich document
                document = f"""
                Security Issue in {filename}
                Line: {issue.get('line', 'N/A')}
                Severity: {issue.get('severity', {}).get('level', 'unknown')}
                Finding: {issue.get('feedback', '')}
                """
                
                metadata = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "filename": filename,
                    "line": issue.get('line', 0),
                    "severity": issue.get('severity', {}).get('level', 'low'),
                    "score": issue.get('severity', {}).get('score', 1),
                    "timestamp": review_data.get('review_time', datetime.now().isoformat()),
                    "type": "security_issue"
                }
                
                self.security_collection.add(
                    documents=[document],
                    metadatas=[metadata],
                    ids=[issue_id]
                )
    
    def get_similar_security_issues(self,
                                   issue_description: str,
                                   user_id: Optional[str] = None,
                                   project_id: Optional[str] = None,
                                   n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Find similar security issues from past reviews
        
        Args:
            issue_description: Description of the issue to search for
            user_id: Filter by user (optional)
            project_id: Filter by project (optional)
            n_results: Number of results to return
            
        Returns:
            List of similar security issues
        """
        where_filter = {"type": "security_issue"}
        if user_id:
            where_filter["user_id"] = user_id
        if project_id:
            where_filter["project_id"] = project_id
        
        results = self.security_collection.query(
            query_texts=[issue_description],
            where=where_filter if where_filter else None,
            n_results=n_results
        )
        
        return self._format_results(results)
        
    def store_logic_review(self,
                          user_id: str,
                          submission_id: str,
                          project_id: str,
                          review_data: Dict[str, Any]):
        """
        Store logic review findings
        
        Args:
            user_id: User ID
            submission_id: Submission ID
            project_id: Project ID
            review_data: Logic review JSON data
        """
        review_id = self._generate_id(user_id, submission_id, datetime.now().isoformat())
        
        files = review_data.get('files', [])
        for file_idx, file_data in enumerate(files):
            errors = file_data.get('logic Errors', [])
            
            for error_idx, error in enumerate(errors):
                error_id = f"{review_id}_file{file_idx}_error{error_idx}"
                
                document = f"""
                Logic Error in function: {error.get('function', 'unknown')}
                Issue: {error.get('feedback', '')}
                """
                
                metadata = {
                    "user_id": user_id,
                    "submission_id": submission_id,
                    "project_id": project_id,
                    "function": error.get('function', 'unknown'),
                    "timestamp": review_data.get('review_time', datetime.now().isoformat()),
                    "type": "logic_error"
                }
                
                self.logic_collection.add(
                    documents=[document],
                    metadatas=[metadata],
                    ids=[error_id]
                )
    
    def get_similar_logic_errors(self,
                                error_description: str,
                                user_id: Optional[str] = None,
                                n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Find similar logic errors from past reviews
        """
        where_filter = {"type": "logic_error"}
        if user_id:
            where_filter["user_id"] = user_id
        
        results = self.logic_collection.query(
            query_texts=[error_description],
            where=where_filter if where_filter else None,
            n_results=n_results
        )
        
        return self._format_results(results)
    
    
    def store_user_interaction(self,
                              user_id: str,
                              interaction_type: str,
                              context: str,
                              metadata: Optional[Dict[str, Any]] = None):
        """
        Store user interaction for context learning
        
        Args:
            user_id: User ID
            interaction_type: Type of interaction (e.g., 'preference', 'query', 'feedback')
            context: Context text
            metadata: Additional metadata
        """
        interaction_id = self._generate_id(user_id, datetime.now().isoformat())
        
        meta = {
            "user_id": user_id,
            "interaction_type": interaction_type,
            "timestamp": datetime.now().isoformat(),
            "type": "user_interaction"
        }
        if metadata:
            meta.update(metadata)
        
        self.user_collection.add(
            documents=[context],
            metadatas=[meta],
            ids=[interaction_id]
        )
    
    def get_user_context(self,
                        user_id: str,
                        query: str,
                        n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant user context
        """
        results = self.user_collection.query(
            query_texts=[query],
            where={"user_id": user_id, "type": "user_interaction"},
            n_results=n_results
        )
        
        return self._format_results(results)
    
    # ==================== PROJECT CONTEXT MEMORY ====================
    
    def store_project_context(self,
                             user_id: str,
                             project_id: str,
                             project_name: str,
                             project_desc: str,
                             file_structure: List[str]):
        """
        Store project-level context
        
        Args:
            user_id: User ID
            project_id: Project ID
            project_name: Project name
            project_desc: Project description
            file_structure: List of file paths in the project
        """
        doc_id = self._generate_id(user_id, project_id)
        
        document = f"""
        Project: {project_name}
        Description: {project_desc}
        Files: {', '.join(file_structure)}
        """
        
        metadata = {
            "user_id": user_id,
            "project_id": project_id,
            "project_name": project_name,
            "file_count": len(file_structure),
            "timestamp": datetime.now().isoformat(),
            "type": "project_context"
        }
        
        self.project_collection.add(
            documents=[document],
            metadatas=[metadata],
            ids=[doc_id]
        )
    
    def get_project_context(self,
                           user_id: str,
                           project_id: str) -> Optional[Dict[str, Any]]:
        """
        Get project context
        """
        doc_id = self._generate_id(user_id, project_id)
        
        try:
            result = self.project_collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"]
            )
            
            if result['ids']:
                return {
                    'document': result['documents'][0],
                    'metadata': result['metadatas'][0]
                }
        except Exception:
            pass
        
        return None
        
    def get_enhanced_context(self,
                           user_id: str,
                           project_id: str,
                           current_code: str,
                           review_type: str = "security") -> Dict[str, Any]:
        """
        Get comprehensive context for AI review
        
        Args:
            user_id: User ID
            project_id: Project ID
            current_code: Current code being reviewed
            review_type: Type of review (security, logic, testing)
            
        Returns:
            Dictionary with enhanced context for AI
        """
        context = {
            "similar_code": [],
            "past_issues": [],
            "project_context": None,
            "user_preferences": []
        }
        
        # Get similar code
        context["similar_code"] = self.get_similar_code(
            current_code,
            user_id=user_id,
            project_id=project_id,
            n_results=3
        )
        
        # Get past issues based on review type
        if review_type == "security":
            context["past_issues"] = self.get_similar_security_issues(
                current_code,
                user_id=user_id,
                project_id=project_id,
                n_results=3
            )
        elif review_type == "logic":
            context["past_issues"] = self.get_similar_logic_errors(
                current_code,
                user_id=user_id,
                n_results=3
            )
        
        # Get project context
        context["project_context"] = self.get_project_context(user_id, project_id)
        
        # Get user preferences
        context["user_preferences"] = self.get_user_context(
            user_id,
            f"preferences for {review_type} review",
            n_results=2
        )
        
        return context
    
    
    def _format_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format ChromaDB query results into a cleaner structure"""
        formatted = []
        
        if not results['ids'] or not results['ids'][0]:
            return formatted
        
        for i in range(len(results['ids'][0])):
            formatted.append({
                'id': results['ids'][0][i],
                'document': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i] if 'distances' in results else None
            })
        
        return formatted
    
    def clear_user_data(self, user_id: str):
        """Clear all data for a specific user (GDPR compliance)"""
        collections = [
            self.code_collection,
            self.security_collection,
            self.logic_collection,
            self.user_collection,
            self.project_collection
        ]
        
        for collection in collections:
            # Get all documents for this user
            results = collection.get(
                where={"user_id": user_id},
                include=[]
            )
            
            if results['ids']:
                collection.delete(ids=results['ids'])
    
    def get_collection_stats(self) -> Dict[str, int]:
        """Get statistics about stored data"""
        return {
            "code_submissions": self.code_collection.count(),
            "security_reviews": self.security_collection.count(),
            "logic_reviews": self.logic_collection.count(),
            "user_interactions": self.user_collection.count(),
            "projects": self.project_collection.count()
        }
