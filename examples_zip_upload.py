#!/usr/bin/env python3
"""
Examples of using the RAG System ZIP upload endpoints

This script demonstrates how to use the new zip upload functionality
"""

import requests
import json
from pathlib import Path


BASE_URL = "http://localhost:8000"


def example_zip_upload(zip_file_path: str):
    """
    Example 1: Upload and extract a zip file
    
    This endpoint:
    - Accepts a .zip file
    - Extracts only code files (filters out binary files)
    - Returns list of extracted files with metadata
    """
    print("\n=== Example 1: Upload ZIP ===")
    
    with open(zip_file_path, 'rb') as f:
        files = {'file': (Path(zip_file_path).name, f, 'application/zip')}
        response = requests.post(f"{BASE_URL}/api/upload/zip", files=files)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Upload successful")
        print(f"  Upload ID: {result['upload_id']}")
        print(f"  Zip file size: {result['zip_size']:,} bytes")
        print(f"  Extracted files: {result['extracted_files_count']}")
        print(f"  Total extracted size: {result['total_extracted_size']:,} bytes")
        print(f"  Temp directory: {result['temp_directory']}")
        
        print(f"\n  Extracted files:")
        for file in result['extracted_files']:
            print(f"    - {file['relative_path']} ({file['size']} bytes, {file['file_type']})")
        
        return result['upload_id'], result['temp_directory']
    else:
        print(f"✗ Upload failed: {response.status_code}")
        print(f"  Error: {response.json()}")
        return None, None


def example_zip_process(upload_id: str):
    """
    Example 2: Process extracted zip files
    
    This endpoint:
    - Parses code in each extracted file
    - Generates embeddings
    - Stores in vector database
    """
    print(f"\n=== Example 2: Process ZIP ({upload_id}) ===")
    
    response = requests.post(
        f"{BASE_URL}/api/upload/zip/process",
        params={"upload_id": upload_id}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Processing queued successfully")
        print(f"  Status: {result['status']}")
        print(f"  Files queued: {result['files_queued']}")
        print(f"  Message: {result['message']}")
        print(f"\n  Files are being processed in the background")
    else:
        print(f"✗ Processing failed: {response.status_code}")
        print(f"  Error: {response.json()}")


def example_zip_cleanup(upload_id: str):
    """
    Example 3: Clean up temporary directory
    
    This endpoint:
    - Removes temporary extraction directory
    - Frees up disk space
    """
    print(f"\n=== Example 3: Cleanup ZIP ({upload_id}) ===")
    
    response = requests.delete(f"{BASE_URL}/api/upload/zip/{upload_id}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Cleanup successful")
        print(f"  Status: {result['status']}")
        print(f"  Message: {result['message']}")
    else:
        print(f"✗ Cleanup failed: {response.status_code}")
        print(f"  Error: {response.json()}")


def example_filtering_demo():
    """
    Example 4: Show file filtering in action
    
    The zip extractor filters files:
    - KEEPS: .py, .js, .ts, .java, .cpp, .go, .rs, .rb, .sql, etc.
    - KEEPS: .json, .yaml, .yml, .html, .css, .xml files
    - KEEPS: Scripts with no extension (if valid)
    - IGNORES: .pyc, .class, .jar, .exe, .dll files
    - IGNORES: Images (.png, .jpg, .gif, etc.)
    - IGNORES: Compressed files (.zip, .rar, .tar.gz, etc.)
    - IGNORES: Binary files (.mp3, .mp4, .pdf, etc.)
    """
    print("\n=== File Filtering ===")
    print("The zip extractor automatically:")
    print("  ✓ KEEPS code files (.py, .js, .ts, .java, .cpp, .go, .rs, .rb, etc.)")
    print("  ✓ KEEPS config files (.json, .yaml, .yml, .xml, etc.)")
    print("  ✓ KEEPS markup files (.html, .css, .md, etc.)")
    print("  ✗ IGNORES compiled files (.pyc, .class, .jar, .exe, .dll, .so, etc.)")
    print("  ✗ IGNORES images (.png, .jpg, .jpeg, .gif, .bmp, etc.)")
    print("  ✗ IGNORES archives (.zip, .rar, .7z, .tar.gz, etc.)")
    print("  ✗ IGNORES media (.mp3, .mp4, .avi, .wav, etc.)")
    print("  ✗ IGNORES documents (.pdf, .doc, .xls, etc.)")
    print("  ✗ IGNORES hidden files (.*)")


def create_example_zip():
    """Create a simple example zip file for testing"""
    import zipfile
    import io
    
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        # Add code files
        zf.writestr('src/app.py', '''
def main():
    print("Hello from Python")

if __name__ == "__main__":
    main()
''')
        zf.writestr('src/handler.js', '''
function processData(data) {
  console.log("Processing:", data);
  return data.map(x => x * 2);
}

module.exports = { processData };
''')
        
        zf.writestr('config.json', '''
{
  "name": "example",
  "version": "1.0.0"
}
''')
        
        # Add binary files that should be ignored
        zf.writestr('images/logo.png', b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)  # PNG header
        zf.writestr('compiled/App.class', b'\xca\xfe\xba\xbe' + b'\x00' * 100)  # Java class file
    
    zip_buffer.seek(0)
    with open('example.zip', 'wb') as f:
        f.write(zip_buffer.read())
    
    print("✓ Created example.zip")
    return 'example.zip'


def main():
    """Run all examples"""
    print("RAG System ZIP Upload Examples")
    print("=" * 50)
    
    # Show filtering demo
    example_filtering_demo()
    
    # Create example zip
    zip_file = create_example_zip()
    
    # Upload
    upload_id, temp_dir = example_zip_upload(zip_file)
    
    if upload_id:
        # Process
        example_zip_process(upload_id)
        
        # Cleanup
        input("\nPress Enter to cleanup temporary files...")
        example_zip_cleanup(upload_id)
    
    print("\n" + "=" * 50)
    print("Examples completed!")


if __name__ == "__main__":
    main()
