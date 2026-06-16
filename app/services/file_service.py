"""File upload and management service"""

import os
import uuid
import logging
from pathlib import Path
from typing import Tuple

from app.utils.config import get_settings

logger = logging.getLogger(__name__)


class FileService:
    """Handle file uploads and storage"""
    
    def __init__(self):
        self.settings = get_settings()
        self.upload_dir = Path(self.settings.UPLOAD_DIR)
        self.upload_dir.mkdir(exist_ok=True)
    
    async def save_upload_file(self, filename: str, content: bytes) -> Tuple[str, str]:
        """
        Save uploaded file to disk
        
        Args:
            filename: Original filename
            content: File content bytes
            
        Returns:
            Tuple of (file_id, file_path)
        """
        # Validate file size
        if len(content) > self.settings.MAX_FILE_SIZE:
            raise ValueError(
                f"File size exceeds maximum allowed: "
                f"{len(content)} > {self.settings.MAX_FILE_SIZE}"
            )
        
        # Validate extension
        ext = Path(filename).suffix.lower()
        if ext not in self.settings.ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File type not allowed: {ext}. "
                f"Allowed: {self.settings.ALLOWED_EXTENSIONS}"
            )
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        file_path = self.upload_dir / f"{file_id}_{filename}"
        
        # Write file
        try:
            with open(file_path, 'wb') as f:
                f.write(content)
            logger.info(f"File saved: {file_path}")
            return file_id, str(file_path)
        except IOError as e:
            logger.error(f"Failed to save file: {e}")
            raise
    
    async def read_file(self, file_id: str, filename: str) -> bytes:
        """
        Read uploaded file content
        
        Args:
            file_id: File identifier
            filename: Original filename
            
        Returns:
            File content bytes
        """
        file_path = self.upload_dir / f"{file_id}_{filename}"
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except IOError as e:
            logger.error(f"Failed to read file: {e}")
            raise
    
    async def delete_file(self, file_id: str, filename: str) -> bool:
        """
        Delete uploaded file
        
        Args:
            file_id: File identifier
            filename: Original filename
            
        Returns:
            True if successful
        """
        file_path = self.upload_dir / f"{file_id}_{filename}"
        
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"File deleted: {file_path}")
                return True
            return False
        except IOError as e:
            logger.error(f"Failed to delete file: {e}")
            raise


# Global service instance
_file_service: FileService | None = None


def get_file_service() -> FileService:
    """Get file service instance"""
    global _file_service
    if _file_service is None:
        _file_service = FileService()
    return _file_service
