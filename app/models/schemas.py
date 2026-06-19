"""Data schemas and Pydantic models"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """Response model for file upload"""
    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Name of the uploaded file")
    size: int = Field(..., description="File size in bytes")
    chunks: int = Field(..., description="Number of chunks created")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CodeChunk(BaseModel):
    """Represents a chunk of code"""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    content: str = Field(..., description="Code chunk content")
    language: str = Field(..., description="Programming language")
    start_line: int = Field(..., description="Starting line number")
    end_line: int = Field(..., description="Ending line number")
    file_id: str = Field(..., description="Reference to source file")


class EmbeddingResult(BaseModel):
    """Result of embedding generation"""
    chunk_id: str
    embedding: List[float] = Field(..., description="Embedding vector")
    similarity_score: Optional[float] = None


class QueryRequest(BaseModel):
    """Request model for querying the RAG system"""
    query: str = Field(..., min_length=1, description="Search query or question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")
    filters: Optional[dict] = Field(default=None, description="Optional filters")
    session_id: Optional[str] = Field(default=None, description="Browser session identifier")
    gemini_api_key: Optional[str] = Field(
        default=None,
        description="User's Google Gemini API key (not stored server-side)",
    )


class ProjectOverviewResponse(BaseModel):
    """Project summary and suggested questions after indexing"""
    ready: bool = False
    description: str = ""
    sample_questions: List[str] = Field(default_factory=list)
    total_chunks: int = 0
    total_files: int = 0


class RetrievedContext(BaseModel):
    """Retrieved context for LLM"""
    chunk_id: str
    content: str
    language: str
    file_id: str
    file_path: str = ""
    filename: str = ""
    function_name: str = ""
    class_name: str = ""
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    similarity_score: float
    expansion_type: Optional[str] = None
    context_group: Optional[str] = None


class QueryResponse(BaseModel):
    """Response model for query endpoint"""
    answer: str = Field(..., description="LLM-generated answer")
    context: List[RetrievedContext] = Field(..., description="Retrieved context chunks")
    relevant_file_names: List[str] = Field(default_factory=list, description="Relevant file names")
    retrieved_snippets: List[RetrievedContext] = Field(default_factory=list, description="Retrieved snippets from the query")
    model: str = Field(..., description="Model used for generation")
    tokens_used: int = Field(default=0, description="Tokens consumed")


class FileListResponse(BaseModel):
    """Response for listing uploaded files"""
    files: List[FileUploadResponse]
    total_files: int
    total_chunks: int


class ExtractedFile(BaseModel):
    """Represents an extracted file from zip"""
    filename: str = Field(..., description="Original filename")
    relative_path: str = Field(..., description="Path relative to zip root")
    absolute_path: str = Field(..., description="Absolute path in temp directory")
    size: int = Field(..., description="File size in bytes")
    file_type: str = Field(..., description="File extension")
    extracted_at: str = Field(..., description="Extraction timestamp")


class ZipUploadResponse(BaseModel):
    """Response model for zip file upload"""
    upload_id: str = Field(..., description="Unique upload identifier")
    filename: str = Field(..., description="Original zip filename")
    zip_size: int = Field(..., description="Original zip file size")
    extracted_files_count: int = Field(..., description="Number of extracted code files")
    total_extracted_size: int = Field(..., description="Total size of extracted files")
    extracted_files: List[ExtractedFile] = Field(..., description="List of extracted files")
    temp_directory: str = Field(..., description="Temporary extraction directory")
    created_at: datetime = Field(default_factory=datetime.utcnow)
