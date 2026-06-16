"""Zip file extraction and handling utilities"""

import os
import logging
import tempfile
import zipfile
import stat
import shutil
from pathlib import Path
from typing import List, Tuple, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


# Binary file extensions to ignore
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.exe', '.dll', '.so', '.dylib', '.o', '.obj',
    '.pyc', '.pyo', '.class', '.jar', '.war',
    '.mp3', '.mp4', '.avi', '.mov', '.wav',
    '.zip', '.rar', '.7z', '.tar', '.gz',
}

# Code file extensions to keep
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx',
    '.java', '.cpp', '.c', '.h', '.hpp',
    '.go', '.rs', '.rb', '.php', '.swift',
    '.kt', '.scala', '.pl', '.sh', '.bash',
    '.yaml', '.yml', '.json', '.xml', '.html', '.css',
    '.sql', '.r', '.m', '.groovy',
}


class ZipExtractor:
    """Safe zip file extraction with filtering"""
    
    def __init__(self, max_file_size: int = 50 * 1024 * 1024):
        """
        Initialize zip extractor
        
        Args:
            max_file_size: Maximum allowed file size in bytes
        """
        self.max_file_size = max_file_size
        self.max_entries = 2000
        self.max_total_uncompressed_size = 200 * 1024 * 1024
        self.max_path_depth = 20
        self.max_filename_length = 240
    
    def is_code_file(self, filename: str) -> bool:
        """
        Check if file is a code file
        
        Args:
            filename: File name to check
            
        Returns:
            True if file extension is in code extensions
        """
        ext = Path(filename).suffix.lower()
        return ext in CODE_EXTENSIONS
    
    def is_binary_file(self, filename: str) -> bool:
        """
        Check if file is binary (should be ignored)
        
        Args:
            filename: File name to check
            
        Returns:
            True if file is binary
        """
        ext = Path(filename).suffix.lower()
        return ext in BINARY_EXTENSIONS
    
    def should_extract(self, filename: str) -> bool:
        """
        Determine if file should be extracted
        
        Args:
            filename: File name to check
            
        Returns:
            True if file should be extracted
        """
        # Skip directories
        if filename.endswith('/'):
            return False
        
        # Skip binary files
        if self.is_binary_file(filename):
            return False
        
        # Skip hidden files and common non-code files
        name = Path(filename).name
        if name.startswith('.') or name.startswith('__'):
            return False
        
        # Keep if it's a code file or has no extension (scripts, config files)
        if self.is_code_file(filename):
            return True
        
        # Allow files with no extension (scripts, makefiles, etc.)
        if Path(filename).suffix == '':
            return True
        
        return False

    @staticmethod
    def _is_symlink(info: zipfile.ZipInfo) -> bool:
        """Detect symlink entries in ZIP metadata."""
        mode = (info.external_attr >> 16) & 0xFFFF
        return stat.S_ISLNK(mode)

    def _is_safe_member_path(self, filename: str) -> bool:
        """Validate archive member path against traversal and abuse patterns."""
        sanitized = filename.replace("\\", "/")
        if not sanitized or sanitized.startswith("/"):
            return False
        if len(sanitized) > self.max_filename_length:
            return False

        parts = [part for part in sanitized.split("/") if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            return False
        if len(parts) > self.max_path_depth:
            return False
        return True
    
    async def extract_zip(self, zip_content: bytes) -> Tuple[str, List[Dict]]:
        """
        Extract zip file safely
        
        Args:
            zip_content: Zip file bytes
            
        Returns:
            Tuple of (temp_dir_path, list of extracted files with metadata)
            
        Raises:
            ValueError: If zip is invalid or unsafe
            OSError: If extraction fails
        """
        # Validate size
        if len(zip_content) > self.max_file_size:
            raise ValueError(
                f"Zip file exceeds maximum size: "
                f"{len(zip_content)} > {self.max_file_size}"
            )
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(prefix='rag_zip_')
        logger.info(f"Created temp directory: {temp_dir}")
        
        extracted_files = []
        
        try:
            # Use BytesIO for zip extraction
            from io import BytesIO
            zip_buffer = BytesIO(zip_content)
            
            with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                # Validate zip integrity
                bad_file = zip_ref.testzip()
                if bad_file is not None:
                    raise ValueError(f"Corrupted zip file: {bad_file}")
                
                members = zip_ref.infolist()
                if len(members) > self.max_entries:
                    raise ValueError(
                        f"Zip archive has too many entries: {len(members)} > {self.max_entries}"
                    )

                total_uncompressed_size = 0

                # Extract files
                for info in members:
                    filename = info.filename

                    if self._is_symlink(info):
                        logger.warning("Skipping symlink entry: %s", filename)
                        continue

                    if not self._is_safe_member_path(filename):
                        logger.warning("Skipping suspicious path: %s", filename)
                        continue

                    target_path = Path(temp_dir) / filename
                    try:
                        target_path.resolve().relative_to(Path(temp_dir).resolve())
                    except ValueError:
                        logger.warning("Skipping traversal attempt: %s", filename)
                        continue

                    # Check if file should be extracted
                    if not self.should_extract(filename):
                        logger.debug(f"Skipping {filename}")
                        continue

                    # Validate individual file size
                    if info.file_size > self.max_file_size:
                        logger.warning(
                            f"Skipping oversized file: {filename} "
                            f"({info.file_size} bytes)"
                        )
                        continue

                    total_uncompressed_size += info.file_size
                    if total_uncompressed_size > self.max_total_uncompressed_size:
                        raise ValueError(
                            "Zip archive uncompressed content exceeds safety limit: "
                            f"{total_uncompressed_size} > {self.max_total_uncompressed_size}"
                        )

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zip_ref.open(info, "r") as src, target_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)

                    extracted_path = str(target_path.resolve())
                    logger.info("Extracted: %s", filename)

                    extracted_files.append({
                        'filename': filename,
                        'relative_path': filename,
                        'absolute_path': extracted_path,
                        'size': info.file_size,
                        'file_type': Path(filename).suffix.lower(),
                        'extracted_at': datetime.utcnow().isoformat()
                    })
            
            logger.info(
                f"Successfully extracted {len(extracted_files)} files "
                f"from zip to {temp_dir}"
            )
            
            return temp_dir, extracted_files
        
        except zipfile.BadZipFile as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError(f"Invalid zip file: {e}")
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.error(f"Zip extraction failed: {e}")
            raise
    
    @staticmethod
    def cleanup_temp_dir(temp_dir: str) -> bool:
        """
        Clean up temporary directory
        
        Args:
            temp_dir: Path to temporary directory
            
        Returns:
            True if successful
        """
        try:
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to cleanup temp dir {temp_dir}: {e}")
            return False
    
    @staticmethod
    def copy_extracted_files(
        source_temp_dir: str,
        dest_upload_dir: str
    ) -> Tuple[str, List[Dict]]:
        """
        Copy extracted files to permanent upload directory
        
        Args:
            source_temp_dir: Temporary extraction directory
            dest_upload_dir: Destination upload directory
            
        Returns:
            Tuple of (upload_dir_id, list of file paths)
        """
        import shutil
        import uuid
        
        upload_id = str(uuid.uuid4())
        dest_path = Path(dest_upload_dir) / upload_id
        dest_path.mkdir(parents=True, exist_ok=True)
        
        copied_files = []
        
        try:
            for root, dirs, files in os.walk(source_temp_dir):
                for file in files:
                    src_file = Path(root) / file
                    
                    # Preserve directory structure
                    rel_path = src_file.relative_to(source_temp_dir)
                    dest_file = dest_path / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    shutil.copy2(src_file, dest_file)
                    copied_files.append({
                        'filename': file,
                        'relative_path': str(rel_path),
                        'absolute_path': str(dest_file),
                        'size': dest_file.stat().st_size,
                        'file_type': dest_file.suffix.lower()
                    })
            
            logger.info(
                f"Copied {len(copied_files)} files to {dest_path}"
            )
            return upload_id, copied_files
        
        except Exception as e:
            logger.error(f"Failed to copy extracted files: {e}")
            shutil.rmtree(dest_path, ignore_errors=True)
            raise


# Global extractor instance
_zip_extractor: ZipExtractor | None = None


def get_zip_extractor(max_file_size: int = 50 * 1024 * 1024) -> ZipExtractor:
    """Get zip extractor instance"""
    global _zip_extractor
    if _zip_extractor is None:
        _zip_extractor = ZipExtractor(max_file_size)
    return _zip_extractor
