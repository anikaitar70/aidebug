"""
Quick start guide for RAG System

This script creates a sample zip file and guides you through testing the system.
"""

import zipfile
import io


def create_sample_zip():
    """Create a sample zip file with example code"""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        # Python file
        zf.writestr('src/main.py', '''"""Main application module"""

def authenticate_user(username, password):
    """Authenticate user with username and password"""
    if not username or not password:
        raise ValueError("Username and password required")
    
    # Check against database
    user = database.get_user(username)
    if not user or not verify_password(password, user.password_hash):
        return None
    
    return user


def create_session(user):
    """Create user session"""
    session = {
        'user_id': user.id,
        'username': user.username,
        'created_at': datetime.now(),
        'expires_at': datetime.now() + timedelta(hours=24)
    }
    cache.store_session(session)
    return session


def verify_password(plain_password, hash_password):
    """Verify password hash"""
    return bcrypt.checkpw(plain_password.encode(), hash_password)
''')
        
        # JavaScript file
        zf.writestr('src/handlers.js', '''// API Request handlers

async function handleLogin(req, res) {
    const { username, password } = req.body;
    
    try {
        const user = await authenticateUser(username, password);
        if (!user) {
            return res.status(401).json({ error: 'Invalid credentials' });
        }
        
        const token = generateJWT(user);
        res.json({ token, user: user.toPublic() });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
}

async function handleGetProfile(req, res) {
    const userId = req.user.id;
    const user = await database.getUser(userId);
    res.json(user.toPublic());
}

function generateJWT(user) {
    return jwt.sign(
        { id: user.id, username: user.username },
        process.env.JWT_SECRET,
        { expiresIn: '24h' }
    );
}
''')
        
        # Config file
        zf.writestr('config.json', '''{
  "name": "Sample RAG Project",
  "version": "1.0.0",
  "description": "Sample codebase for RAG System testing",
  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "rag_sample"
  },
  "jwt_secret": "your-secret-key-here"
}
''')
        
        # HTML file
        zf.writestr('public/index.html', '''<!DOCTYPE html>
<html>
<head>
    <title>Sample App</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="container">
        <h1>Welcome</h1>
        <form id="loginForm">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
    </div>
    <script src="app.js"></script>
</body>
</html>
''')
        
        # README
        zf.writestr('README.md', '''# Sample Project

This is a sample project for testing the RAG System.

## Features

- User authentication with JWT
- Session management
- Password hashing with bcrypt
- RESTful API endpoints

## Example Queries

Try asking the RAG system:

1. "How does user authentication work?"
2. "Show me the login handler function"
3. "What database configuration is used?"
4. "How are sessions created?"
5. "What files contain authentication logic?"
''')
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def main():
    """Create and save sample zip file"""
    print("Creating sample project zip file...")
    
    zip_data = create_sample_zip()
    
    with open('sample_project.zip', 'wb') as f:
        f.write(zip_data)
    
    print(f"✓ Created sample_project.zip ({len(zip_data):,} bytes)")
    print("\nNext steps:")
    print("1. Start the RAG API: python main.py")
    print("2. Open index.html in a web browser")
    print("3. Upload sample_project.zip")
    print("4. Try a query like: 'How does user authentication work?'")


if __name__ == '__main__':
    main()
