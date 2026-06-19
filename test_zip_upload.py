"""
Unit tests for ZIP upload functionality

Run with: pytest test_zip_upload.py
"""

import pytest
import tempfile
import zipfile
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent))


@pytest.mark.asyncio
class TestZipExtractor:
    """Test the ZipExtractor utility"""
    
    @pytest.fixture
    def zip_extractor(self):
        """Create zip extractor instance"""
        from app.utils.zip_handler import ZipExtractor
        return ZipExtractor()
    
    @pytest.fixture
    def sample_zip(self):
        """Create a sample zip file"""
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            # Add code files
            zf.writestr('src/main.py', 'print("hello")')
            zf.writestr('src/util.js', 'console.log("test")')
            zf.writestr('config.json', '{"key": "value"}')
            
            # Add binary files to ignore
            zf.writestr('images/logo.png', b'\x89PNG\r\n\x1a\n')
            zf.writestr('compiled/App.class', b'\xca\xfe\xba\xbe')
            zf.writestr('data.pyc', b'\x03\xf3\r\n')
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    def test_is_code_file(self, zip_extractor):
        """Test code file detection"""
        assert zip_extractor.is_code_file('script.py') == True
        assert zip_extractor.is_code_file('app.js') == True
        assert zip_extractor.is_code_file('index.html') == True
        assert zip_extractor.is_code_file('image.png') == False
        assert zip_extractor.is_code_file('compiled.class') == False
    
    def test_is_binary_file(self, zip_extractor):
        """Test binary file detection"""
        assert zip_extractor.is_binary_file('image.png') == True
        assert zip_extractor.is_binary_file('image.jpg') == True
        assert zip_extractor.is_binary_file('compiled.pyc') == True
        assert zip_extractor.is_binary_file('app.class') == True
        assert zip_extractor.is_binary_file('script.py') == False
        assert zip_extractor.is_binary_file('app.js') == False
    
    def test_should_extract(self, zip_extractor):
        """Test file extraction decision"""
        # Should extract
        assert zip_extractor.should_extract('src/main.py') == True
        assert zip_extractor.should_extract('config.json') == True
        assert zip_extractor.should_extract('Makefile') == True
        
        # Should not extract
        assert zip_extractor.should_extract('images/') == False  # Directory
        assert zip_extractor.should_extract('image.png') == False
        assert zip_extractor.should_extract('.gitignore') == False  # Hidden
        assert zip_extractor.should_extract('compiled.pyc') == False
    
    @pytest.mark.asyncio
    async def test_extract_zip(self, zip_extractor, sample_zip):
        """Test zip extraction"""
        temp_dir, files = await zip_extractor.extract_zip(sample_zip)
        
        try:
            # Check extraction succeeded
            assert temp_dir is not None
            assert Path(temp_dir).exists()
            assert len(files) > 0
            
            # Check filtered results (should have 3 code files, not 5)
            filenames = [f['filename'] for f in files]
            assert 'main.py' in filenames or 'src/main.py' in str(files)
            assert 'util.js' in filenames or 'src/util.js' in str(files)
            assert 'config.json' in filenames
            
            # Binary files should be filtered out
            all_files = [f['filename'] for f in files]
            assert not any('logo.png' in f for f in all_files)
            assert not any('App.class' in f for f in all_files)
            assert not any('.pyc' in f for f in all_files)
        
        finally:
            # Cleanup
            zip_extractor.cleanup_temp_dir(temp_dir)
            assert not Path(temp_dir).exists()
    
    @pytest.mark.asyncio
    async def test_extract_zip_invalid(self, zip_extractor):
        """Test extraction with invalid zip"""
        invalid_zip = b'not a zip file'
        
        with pytest.raises(ValueError, match="Invalid zip file"):
            await zip_extractor.extract_zip(invalid_zip)
    
    @pytest.mark.asyncio
    async def test_extract_zip_size_limit(self, zip_extractor):
        """Test extraction with size limit"""
        # Create zip that exceeds size limit
        extractor = zip_extractor
        extractor.max_file_size = 100  # 100 bytes limit
        
        large_zip = io.BytesIO()
        with zipfile.ZipFile(large_zip, 'w') as zf:
            zf.writestr('large_file.py', 'x' * 1000)
        
        large_zip.seek(0)
        
        with pytest.raises(ValueError, match="exceeds maximum size"):
            await extractor.extract_zip(large_zip.getvalue())
    
    def test_cleanup_temp_dir(self, zip_extractor):
        """Test temporary directory cleanup"""
        # Create temp dir
        temp_dir = tempfile.mkdtemp()
        assert Path(temp_dir).exists()
        
        # Cleanup
        result = zip_extractor.cleanup_temp_dir(temp_dir)
        assert result == True
        assert not Path(temp_dir).exists()
    
    def test_cleanup_nonexistent_dir(self, zip_extractor):
        """Test cleanup of nonexistent directory"""
        result = zip_extractor.cleanup_temp_dir('/nonexistent/path')
        assert result == False


@pytest.mark.asyncio
class TestFileFiltering:
    """Test file filtering logic"""
    
    @pytest.fixture
    def zip_extractor(self):
        from app.utils.zip_handler import ZipExtractor
        return ZipExtractor()
    
    def test_language_extensions(self, zip_extractor):
        """Test that all language extensions are filtered correctly"""
        code_files = [
            'app.py', 'script.js', 'main.ts', 'App.java',
            'main.cpp', 'utils.go', 'lib.rs', 'config.json'
        ]
        
        for file in code_files:
            assert zip_extractor.should_extract(file) == True, f"Should extract {file}"
    
    def test_binary_extensions(self, zip_extractor):
        """Test that binary extensions are filtered"""
        binary_files = [
            'image.png', 'photo.jpg', 'video.mp4', 'archive.zip',
            'compiled.pyc', 'java_class.class', 'library.so'
        ]
        
        for file in binary_files:
            assert zip_extractor.should_extract(file) == False, f"Should not extract {file}"
    
    def test_hidden_files(self, zip_extractor):
        """Test that hidden files are filtered"""
        hidden_files = ['.gitignore', '.env', '.hidden.py', '__pycache__']
        
        for file in hidden_files:
            assert zip_extractor.should_extract(file) == False, f"Should not extract {file}"

    def test_excluded_directories(self, zip_extractor):
        """Test that dependency and build directories are excluded"""
        excluded = [
            'node_modules/lodash/index.js',
            'frontend/dist/bundle.min.js',
            'build/output.js',
            'coverage/lcov.info',
            '.next/static/chunk.js',
            'venv/lib/python3.11/site.py',
            '.git/config',
            'package-lock.json',
            'yarn.lock',
        ]
        for file in excluded:
            assert zip_extractor.should_extract(file) == False, f"Should not extract {file}"


class TestZipHandlerIntegration:
    """Integration tests for zip handler"""
    
    def test_create_sample_zip(self):
        """Test creation of sample zip"""
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w') as zf:
            zf.writestr('src/app.py', 'def main(): pass')
            zf.writestr('README.md', '# Project')
            zf.writestr('image.png', b'\x89PNG')
        
        zip_buffer.seek(0)
        assert len(zip_buffer.getvalue()) > 0
        
        # Verify it's a valid zip
        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            names = zf.namelist()
            assert 'src/app.py' in names
            assert 'README.md' in names
            assert 'image.png' in names


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Setup logging for tests"""
    import logging
    logging.basicConfig(level=logging.DEBUG)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
