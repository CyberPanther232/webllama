from flask import Flask
from authlib.integrations.flask_client import OAuth
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import timedelta
from pathlib import Path

app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static')
oauth = OAuth(app)
bcrypt = Bcrypt(app)

database_path = Path(
    os.getenv('DATABASE_PATH') or os.path.join(app.root_path, 'backend', 'data', 'webllama.db')
).resolve()
database_path.parent.mkdir(parents=True, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{database_path.as_posix()}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['OLLAMA_CONTEXT_WINDOW'] = max(1024, int(os.getenv('OLLAMA_CONTEXT_WINDOW', '4096')))

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or os.urandom(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', '').lower() == 'true'

db = SQLAlchemy(app)

from .backend.ollama import get_connection_info, test_api_connection
from .backend.database import initialize_defaults, migrate_schema

# init_db(database_path)
with app.app_context():
    db.create_all()
    migrate_schema()
    initialize_defaults()
    ollama_base_url = os.getenv('OLLAMA_BASE_URL') or get_connection_info()

test_api_connection(ollama_base_url)

from .backend import routes


@app.context_processor
def inject_template_context():
    from .backend.auth import get_csrf_token, get_current_user
    return {"csrf_token": get_csrf_token(), "current_user": get_current_user()}