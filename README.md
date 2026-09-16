# Webllama

Webllama is a Flask web interface for chatting with Ollama models. It keeps chat history in a local SQLite database and supports local accounts, optional OIDC sign-in, per-user Ollama connections, and model management.

## Features

- Chat with models served by Ollama.
- Create separate conversations with locally stored history and automatic titles.
- Configure a per-user Ollama endpoint and select an installed model.
- View, pull, and remove Ollama models from the web interface.
- Set the chat context window from 1,024 to 32,768 tokens.
- Sign in with a local account or optional Google, Microsoft, or custom OIDC provider.

## Prerequisites

- Python 3.10 or later
- [Ollama](https://ollama.com/) running locally or on a reachable network host

Install at least one Ollama model before starting a chat. For example:

```powershell
ollama pull llama3.2
```

## Run locally

From the repository root, create and activate a virtual environment:

#### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### Linux

```bash
python3 -m venv .venv
.\venv\bin\activate
```

Install the application dependencies:

```powershell
python -m pip install Flask Flask-SQLAlchemy Flask-Bcrypt Authlib requests openai
```

Start Webllama:

```powershell
python -m flask --app app run --debug
```

Open `http://127.0.0.1:5000`, create an account, then open **Settings** to test and save the Ollama server URL. The default is `http://localhost:11434`.

## Run with Docker

Docker Compose starts Webllama, Ollama, and persistent volumes for both the application database and downloaded models:

```powershell
$env:SECRET_KEY = "replace-with-a-long-random-secret"
docker compose up --build -d
```

Open `http://127.0.0.1:5000`. In the container network, Webllama automatically connects to Ollama at `http://ollama:11434`.

Pull a model through the Webllama **Models** page, or run:

```powershell
docker compose exec ollama ollama pull llama3.2
```

To use a different web port, set `WEBLLAMA_PORT` before starting Compose. GPU access is configured for NVIDIA-enabled Docker installations; remove the `deploy.resources` block in `docker-compose.yml` to run Ollama without it.

## Configuration

All configuration is optional. Environment variables take precedence over saved values where applicable.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | None | Forces the Ollama server URL for every user. |
| `OLLAMA_CONTEXT_WINDOW` | `4096` | Default Ollama context-window setting in tokens. |
| `DATABASE_PATH` | `app/backend/data/webllama.db` | SQLite database location. |
| `SECRET_KEY` | Random at startup | Flask session-signing key. Set a stable secret outside development. |
| `SESSION_COOKIE_SECURE` | `false` | Set to `true` when serving over HTTPS. |

When using `flask run`, pass a custom bind address or port with Flask CLI options, for example:

```powershell
python -m flask --app app run --host 0.0.0.0 --port 8000
```

## OIDC sign-in

OIDC is enabled only when the issuer, client ID, redirect URI, and `OAUTH_CLIENT_SECRET` are configured. Set the client secret in the environment and enter the remaining values in **Settings**, or provide them all as environment variables:

```powershell
$env:OAUTH_PROVIDER = "google"
$env:OAUTH_CLIENT_ID = "your-client-id"
$env:OAUTH_REDIRECT_URI = "http://127.0.0.1:5000/auth/callback"
$env:OAUTH_CLIENT_SECRET = "your-client-secret"
```

Supported provider values are `google`, `microsoft`, and `custom`. A custom provider also requires `OAUTH_PLATFORM_NAME` and `OAUTH_ISSUER_URL`.

## Data and security notes

- The default SQLite database is created automatically at `app/backend/data/webllama.db`.
- Local account passwords are hashed with Bcrypt.
- State-changing routes use CSRF protection.
- Chat records are associated with the signed-in user.
- Do not commit `.env` files, database files, or production secrets.

## Project structure

```text
app/
  backend/       Flask routes, authentication, database, and Ollama client
  frontend/      Jinja templates and static assets
  __init__.py    Flask application setup
```
