# Getting Started with RAG System

Complete step-by-step guide to get the RAG system up and running.

## Prerequisites

- Python 3.10+ (3.13 recommended)
- pip package manager

## Installation

### 1. Navigate to Project Directory

```powershell
cd "c:\Users\anika\Desktop\New folder (4)\AI Debug"
```

### 2. Create Virtual Environment (Optional but Recommended)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Setup

### 1. Configure Environment

```powershell
# Copy example config
cp .env.example .env

# Edit .env if needed (for OpenAI API key)
# notepad .env
```

### 2. Create Sample Project

```powershell
python create_sample_project.py
```

This creates `sample_project.zip` with example code to test against.

## Running the System

### 1. Start the Backend API

```powershell
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Press CTRL+C to quit
```

The API docs are available at: http://localhost:8000/docs

### 2. Open the Frontend

Open `index.html` in your web browser:
```powershell
# Windows
start index.html

# Or manually: File → Open → navigate to index.html
```

## First Test Run

### Step 1: Upload Sample Code

1. In the browser, go to the **Upload Codebase** section
2. Click the upload area or drag `sample_project.zip`
3. Click **Upload** button
4. Wait for "✓ Extracted N code files" message

### Step 2: Ask a Question

1. In the **Ask Question** section, enter one of these:
   - "How does user authentication work?"
   - "Show me the login handler"
   - "What files contain authentication?"
   - "How are passwords verified?"

2. Click **Search** button
3. Wait for results (2-5 seconds)

### Step 3: Review Results

You should see:
- **Answer Tab**: AI-generated explanation
- **Snippets Tab**: Retrieved code with similarity scores
- **Export**: Download results as JSON

## Sample Queries to Try

After uploading `sample_project.zip`, try these:

```
1. "How does user authentication work?"
   → Should find main.py with authenticate_user() function

2. "Show me the login handler"
   → Should find handlers.js with handleLogin() function

3. "What is the database configuration?"
   → Should find config.json with database settings

4. "How are sessions created?"
   → Should find create_session() in main.py

5. "Show me password verification logic"
   → Should find verify_password() function

6. "What API endpoints are available?"
   → Should find handleLogin() and handleGetProfile() in handlers.js
```

## API Endpoints

### Upload Files
```bash
curl -X POST http://localhost:8000/api/upload/zip \
  -F "file=@sample_project.zip"
```

### Search
```bash
curl -X POST http://localhost:8000/api/query/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication",
    "top_k": 5
  }'
```

### Check Health
```bash
curl http://localhost:8000/health
```

## Using with Your Own Code

### 1. Create a Zip File

Collect your source files into a zip:
```powershell
# Windows - using 7-Zip or built-in compression
Compress-Archive -Path "C:\path\to\project\*" -DestinationPath "mycode.zip"
```

### 2. Upload to RAG System

Use the web interface or:
```bash
curl -X POST http://localhost:8000/api/upload/zip \
  -F "file=@mycode.zip"
```

### 3. Search Your Codebase

Ask questions about your code using the web interface or API.

## Troubleshooting

### API Not Starting

```powershell
# Check Python installation
python --version

# Check dependencies
python -m pip list | findstr fastapi

# Try reinstalling
python -m pip install --upgrade -r requirements.txt
```

### Upload Fails

- Max file size is 50MB
- Only .zip files supported
- Ensure zip is not corrupted: `7z t mycode.zip`

### No Results Found

- Ensure files were extracted (check upload confirmation)
- Try simpler queries
- Check code is in supported languages (.py, .js, .ts, .java, .cpp, etc.)

### Slow Response

- First query takes longer (loading models)
- Large codebases take longer to process
- Check internet connection (for OpenAI API calls)

## Advanced Usage

### Processing Multiple Files

```powershell
# Create multiple zips
$files = Get-ChildItem "*.zip"
foreach ($file in $files) {
    # Use curl or web interface to upload each
}
```

### Using Custom Models

Edit `app/utils/config.py`:
```python
LLM_MODEL = "gpt-4"  # Change from gpt-3.5-turbo
EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
```

### Integration with Python

```python
import requests

# Upload
response = requests.post(
    'http://localhost:8000/api/upload/zip',
    files={'file': open('code.zip', 'rb')}
)
upload_id = response.json()['upload_id']

# Search
response = requests.post(
    'http://localhost:8000/api/query/search',
    json={
        'query': 'authentication function',
        'top_k': 5
    }
)
results = response.json()
print(results['answer'])
```

## Cleaning Up

### Remove Temporary Files

```powershell
# Clean uploads
Remove-Item -Recurse "uploads" -ErrorAction SilentlyContinue

# Clean vector database
Remove-Item -Recurse "chroma_data" -ErrorAction SilentlyContinue
```

### Stop the Server

```powershell
# Press Ctrl+C in the terminal where main.py is running
```

## Next Steps

1. ✓ Setup complete
2. Try with sample project
3. Upload your own codebase
4. Explore API endpoints
5. Customize for your needs

## Documentation

- **API Documentation**: http://localhost:8000/docs (Swagger)
- **ZIP Upload Guide**: See ZIP_UPLOAD.md
- **Project README**: README.md
- **Examples**: examples_zip_upload.py

## Support

For issues or questions, check:
- README.md - Project overview
- ZIP_UPLOAD.md - File upload details
- app/utils/config.py - Configuration options
- API Docs - http://localhost:8000/docs

## Performance Tips

1. **Batch uploads**: Process multiple zips at once
2. **Query optimization**: Be specific in your queries
3. **Cache results**: Export and store JSON results
4. **Incremental indexing**: Upload related files together
5. **Resource monitoring**: Watch temp directory size

## Security Notes

⚠️ **For local development only**

Before production deployment:
- Set `DEBUG = False`
- Configure proper CORS origins
- Add authentication/authorization
- Use environment variables for secrets
- Set up proper logging
- Use HTTPS
- Add rate limiting

---

**Happy coding!** 🚀
