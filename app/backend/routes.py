from .. import app, oauth
import json
import os

from flask import Response, abort, flash, jsonify, redirect, send_from_directory, stream_with_context, url_for, render_template, request, session
from authlib.integrations.base_client.errors import OAuthError
from .. import bcrypt
import requests
from .database import add_chat_message, build_chat_context, create_chat, delete_user_chat, get_chat_messages, get_context_window_tokens, get_oauth_settings, get_ollama_connection, get_settings, get_user_chat, get_user_chats, save_oauth_settings, save_ollama_connection, save_selected_model, save_settings, set_chat_title_from_prompt
from .auth import authenticate_user, csrf_protect, get_current_user, get_or_create_oidc_user, login_required, login_user, logout_user, register_user, safe_next_url
from .ollama import OllamaRequestError, delete_ollama_model, generate_chat_response, list_ollama_models, pull_ollama_model, stream_chat_response


def get_effective_ollama_connection(user_id: int):
    connection = get_ollama_connection(user_id)
    environment_url = os.getenv("OLLAMA_BASE_URL", "").strip().rstrip("/")
    return environment_url or (connection.base_url if connection else None), connection, bool(environment_url)


def get_effective_oauth_settings() -> tuple[dict[str, str], dict[str, str]]:
    saved_settings = get_oauth_settings()
    environment_names = {
        "oauth_provider": "OAUTH_PROVIDER",
        "oauth_platform_name": "OAUTH_PLATFORM_NAME",
        "oauth_issuer_url": "OAUTH_ISSUER_URL",
        "oauth_client_id": "OAUTH_CLIENT_ID",
        "oauth_redirect_uri": "OAUTH_REDIRECT_URI",
    }
    values = {}
    sources = {}
    for name, environment_name in environment_names.items():
        environment_value = os.getenv(environment_name, "").strip()
        values[name] = environment_value or saved_settings[name]
        sources[name] = "Environment variable" if environment_value else "Saved setting"
    return values, sources


def get_oidc_configuration() -> dict[str, str] | None:
    oauth_settings, _ = get_effective_oauth_settings()
    issuer_defaults = {
        "google": "Google",
        "microsoft": "Microsoft",
    }
    provider = oauth_settings["oauth_provider"]
    issuer_url = oauth_settings["oauth_issuer_url"]
    if provider == "google":
        issuer_url = "https://accounts.google.com"
    elif provider == "microsoft":
        issuer_url = "https://login.microsoftonline.com/common/v2.0"
    if provider not in {"google", "microsoft", "custom"}:
        return None
    if not all((issuer_url, oauth_settings["oauth_client_id"], oauth_settings["oauth_redirect_uri"], os.getenv("OAUTH_CLIENT_SECRET"))):
        return None
    return {
        "provider_name": oauth_settings["oauth_platform_name"] if provider == "custom" else issuer_defaults[provider],
        "issuer_url": issuer_url.rstrip("/"),
        "client_id": oauth_settings["oauth_client_id"],
        "redirect_uri": oauth_settings["oauth_redirect_uri"],
        "client_secret": os.environ["OAUTH_CLIENT_SECRET"],
    }


def get_oidc_login_context() -> dict[str, str | bool]:
    configuration = get_oidc_configuration()
    return {
        "oidc_enabled": configuration is not None,
        "oidc_provider_name": configuration["provider_name"] if configuration else "OIDC provider",
    }


def get_oidc_client(configuration: dict[str, str]):
    oauth.register(
        name="oidc",
        overwrite=True,
        client_id=configuration["client_id"],
        client_secret=configuration["client_secret"],
        server_metadata_url=f"{configuration['issuer_url']}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.create_client("oidc")

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "frontend", "static", "images"),
        "webllama_dark.ico",
        mimetype="image/x-icon",
    )

@app.route('/', methods=["GET"])
def index():
    return render_template('index.html')

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    base_url, connection, from_environment = get_effective_ollama_connection(get_current_user().id)
    oauth_settings, oauth_sources = get_effective_oauth_settings()
    return render_template(
        'settings.html',
        base_url=base_url or "http://localhost:11434",
        base_url_source="Environment variable" if from_environment else "Saved setting",
        settings=get_settings(),
        context_window_tokens=get_context_window_tokens(),
        oauth_settings=oauth_settings,
        oauth_sources=oauth_sources,
    )

@app.route("/about", methods=["GET"])
def about():
    return render_template('about.html')

@app.route("/login", methods=["GET", "POST"])
@csrf_protect
def login():
    if get_current_user() is not None:
        return redirect(url_for("index"))

    if request.method == "POST":
        user = authenticate_user(request.form.get("email", ""), request.form.get("password", ""))
        if user is None:
            flash("Invalid email or password.")
            return render_template("login.html", **get_oidc_login_context()), 401
        login_user(user)
        flash('Logged in successfully.')
        return redirect(safe_next_url(request.args.get("next")) or url_for('index'))

    return render_template("login.html", **get_oidc_login_context())


@app.route("/auth/oidc/login", methods=["GET"])
def oidc_login():
    configuration = get_oidc_configuration()
    if configuration is None:
        flash("OIDC is not fully configured.")
        return redirect(url_for("login"))
    try:
        return get_oidc_client(configuration).authorize_redirect(configuration["redirect_uri"])
    except OAuthError as error:
        flash(f"Could not start OIDC sign-in: {error.description or error.error}.")
        return redirect(url_for("login"))


@app.route("/auth/callback", methods=["GET"])
def oidc_callback():
    configuration = get_oidc_configuration()
    if configuration is None:
        flash("OIDC is not fully configured.")
        return redirect(url_for("login"))
    try:
        token = get_oidc_client(configuration).authorize_access_token()
        claims = token.get("userinfo") or get_oidc_client(configuration).userinfo(token=token)
    except OAuthError as error:
        flash(f"OIDC sign-in was not completed: {error.description or error.error}.")
        return redirect(url_for("login"))
    user, error = get_or_create_oidc_user(configuration["issuer_url"], claims)
    if error:
        flash(error)
        return redirect(url_for("login"))
    login_user(user)
    flash("Logged in successfully.")
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
@csrf_protect
def register():
    if get_current_user() is not None:
        return redirect(url_for("index"))

    if request.method == "POST":
        password = request.form.get('password', '')
        confirmation = request.form.get('confirmation', '')
        if password != confirmation:
            flash('Passwords do not match.')
            return redirect(url_for('register'))

        user, error = register_user(request.form.get('username', ''), request.form.get('email', ''), password)
        if error:
            flash(error)
            return render_template('register.html'), 400
        login_user(user)
        flash('Account created successfully.')
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route("/logout", methods=["POST"])
@login_required
@csrf_protect
def logout():
    logout_user()
    flash("You have been signed out.")
    return redirect(url_for("login"))

@app.route("/new-chat", methods=["POST"])
@login_required
@csrf_protect
def new_chat():
    chat = create_chat(get_current_user().id)
    return redirect(url_for('chat', chat_id=chat.chat_id))


@app.route("/chats", methods=["GET"])
@login_required
def chats():
    base_url, connection, _ = get_effective_ollama_connection(get_current_user().id)
    installed_models = []
    if base_url:
        try:
            installed_models = list_ollama_models(base_url)
        except OllamaRequestError:
            pass
    return render_template(
        "chats.html",
        chats=get_user_chats(get_current_user().id),
        models=installed_models,
        selected_model=connection.selected_model if connection else None,
    )


@app.route("/models", methods=["GET"])
@login_required
def models():
    base_url, connection, _ = get_effective_ollama_connection(get_current_user().id)
    installed_models = []
    error = None
    if base_url:
        try:
            installed_models = list_ollama_models(base_url)
        except OllamaRequestError as request_error:
            error = str(request_error)
    else:
        error = "Configure an Ollama connection in Settings."
    return render_template(
        "models.html",
        models=installed_models,
        error=error,
        selected_model=connection.selected_model if connection else None,
    )

@app.route("/chat/chat_id=<chat_id>", methods=["GET","POST"])
@login_required
def chat(chat_id):
    current_chat = get_user_chat(chat_id, get_current_user().id)
    if current_chat is None:
        abort(404)
    base_url, connection, _ = get_effective_ollama_connection(get_current_user().id)
    installed_models = []
    if base_url:
        try:
            installed_models = list_ollama_models(base_url)
        except OllamaRequestError:
            pass
    return render_template(
        'chat.html',
        chat_id=chat_id,
        chat=current_chat,
        messages=get_chat_messages(current_chat),
        models=installed_models,
        selected_model=connection.selected_model if connection else None,
    )

# Internal API routes
@app.route("/api/send-prompt/chat_id=<chat_id>", methods=["GET", "POST"])
@login_required
@csrf_protect
def send_prompt(chat_id):
    if request.method == "GET":
        return jsonify(error="Use POST to send a prompt."), 405
    chat = get_user_chat(chat_id, get_current_user().id)
    if chat is None:
        return jsonify(error="Chat not found."), 404
    prompt = str((request.get_json(silent=True) or {}).get("prompt", "")).strip()
    if not prompt:
        return jsonify(error="Prompt is required."), 400
    chat = set_chat_title_from_prompt(chat, prompt)
    add_chat_message(chat, "user", prompt)

    base_url, connection, _ = get_effective_ollama_connection(get_current_user().id)
    if base_url is None:
        return jsonify(error="Configure and test an Ollama connection in Settings."), 400
    context_window = get_context_window_tokens()
    messages, context_tokens = build_chat_context(chat, context_window)
    requested_model = str((request.get_json(silent=True) or {}).get("model", "")).strip() or None
    if get_settings()["stream_responses"]:
        def generate_stream():
            response_parts = []
            try:
                for event, model in stream_chat_response(base_url, messages, context_window, requested_model):
                    payload = json.loads(event)
                    content = payload.get("message", {}).get("content", "")
                    if content:
                        response_parts.append(content)
                        yield json.dumps({"content": content}) + "\n"
                    if payload.get("done"):
                        response = "".join(response_parts).strip()
                        if not response:
                            raise OllamaRequestError("Ollama returned an empty response.")
                        add_chat_message(chat, "assistant", response)
                        yield json.dumps({"done": True, "model": model, "title": chat.title, "context_tokens": context_tokens}) + "\n"
            except (OllamaRequestError, ValueError) as error:
                yield json.dumps({"error": str(error)}) + "\n"

        return Response(stream_with_context(generate_stream()), mimetype="application/x-ndjson")
    try:
        response, model = generate_chat_response(base_url, messages, context_window, requested_model)
    except OllamaRequestError as error:
        return jsonify(error=str(error)), 502

    add_chat_message(chat, "assistant", response)
    return jsonify(
        chat_id=chat.chat_id,
        title=chat.title,
        response=response,
        model=model,
        context_tokens=context_tokens,
    )

@app.route("/api/chat-history/chat_id=<chat_id>", methods=["GET"])
@login_required
def chat_history(chat_id):
    chat = get_user_chat(chat_id, get_current_user().id)
    if chat is None:
        return jsonify(error="Chat not found."), 404
    messages = get_chat_messages(chat)
    return jsonify(messages=[{
        "role": message.role,
        "content": message.content,
        "date_created": message.date_created.isoformat(),
    } for message in messages])

@app.route("/api/delete-chat/chat_id=<chat_id>", methods=["POST", "DELETE"])
@login_required
@csrf_protect
def delete_chat(chat_id):
    if not delete_user_chat(chat_id, get_current_user().id):
        return jsonify(error="Chat not found."), 404
    return jsonify(message="Chat deleted.", chat_id=chat_id)


@app.route("/chats/<chat_id>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_chat_form(chat_id):
    if delete_user_chat(chat_id, get_current_user().id):
        flash("Chat deleted successfully.")
    else:
        flash("Chat not found.")
    return redirect(url_for("chats"))

@app.route("/api/list-chats", methods=["GET"])
@login_required
def list_chats():
    chats = get_user_chats(get_current_user().id)
    return jsonify(chats=[{
        "chat_id": chat.chat_id,
        "title": chat.title,
        "date_created": chat.date_created.isoformat() if chat.date_created else None,
    } for chat in chats])


@app.route("/api/models", methods=["GET"])
@login_required
def api_models():
    base_url, _, _ = get_effective_ollama_connection(get_current_user().id)
    if base_url is None:
        return jsonify(error="Configure an Ollama connection in Settings."), 400
    try:
        return jsonify(models=list_ollama_models(base_url))
    except OllamaRequestError as error:
        return jsonify(error=str(error)), 502


@app.route("/api/models/pull", methods=["POST"])
@login_required
@csrf_protect
def pull_model():
    base_url, _, _ = get_effective_ollama_connection(get_current_user().id)
    model_name = str((request.get_json(silent=True) or {}).get("model", ""))
    if base_url is None:
        return jsonify(error="Configure an Ollama connection in Settings."), 400
    try:
        pull_ollama_model(base_url, model_name)
        return jsonify(message="Model installed.", models=list_ollama_models(base_url))
    except OllamaRequestError as error:
        return jsonify(error=str(error)), 502


@app.route("/api/models/<path:model_name>", methods=["DELETE"])
@login_required
@csrf_protect
def delete_model(model_name):
    base_url, connection, _ = get_effective_ollama_connection(get_current_user().id)
    if base_url is None:
        return jsonify(error="Configure an Ollama connection in Settings."), 400
    try:
        delete_ollama_model(base_url, model_name)
    except OllamaRequestError as error:
        return jsonify(error=str(error)), 502
    if connection and connection.selected_model == model_name:
        save_selected_model(get_current_user().id, None)
    return jsonify(message="Model removed.")


@app.route("/api/models/selection", methods=["PUT"])
@login_required
@csrf_protect
def select_model():
    base_url, connection, _ = get_effective_ollama_connection(get_current_user().id)
    model_name = str((request.get_json(silent=True) or {}).get("model", "")).strip()
    if base_url is None or connection is None:
        return jsonify(error="Test and save an Ollama connection first."), 400
    try:
        installed_models = {model.get("name") for model in list_ollama_models(base_url)}
    except OllamaRequestError as error:
        return jsonify(error=str(error)), 502
    if model_name not in installed_models:
        return jsonify(error="The selected model is not installed."), 400
    save_selected_model(get_current_user().id, model_name)
    return jsonify(message="Model selected.", model=model_name)

@app.route("/api/settings", methods=["GET", "PUT"])
@login_required
@csrf_protect
def api_settings():
    user = get_current_user()
    if request.method == "GET":
        base_url, connection, from_environment = get_effective_ollama_connection(user.id)
        oauth_settings, oauth_sources = get_effective_oauth_settings()
        return jsonify({
            "base_url": base_url or "http://localhost:11434",
            "base_url_source": "environment" if from_environment else "saved",
            "selected_model": connection.selected_model if connection else None,
            "keep_conversations_local": get_settings()["keep_conversations_local"],
            "stream_responses": get_settings()["stream_responses"],
            "context_window_tokens": get_context_window_tokens(),
            "oauth": oauth_settings,
            "oauth_sources": oauth_sources,
        })

    payload = request.get_json(silent=True) or {}
    keep_local = payload.get("keep_conversations_local")
    stream_responses = payload.get("stream_responses")
    context_window_tokens = payload.get("context_window_tokens")
    if not isinstance(keep_local, bool) or not isinstance(stream_responses, bool):
        return jsonify(error="Toggle settings values must be booleans."), 400
    if not isinstance(context_window_tokens, int) or not 1024 <= context_window_tokens <= 32768:
        return jsonify(error="Context window must be between 1024 and 32768 tokens."), 400

    oauth_provider = str(payload.get("oauth_provider", "")).strip()
    oauth_platform_name = str(payload.get("oauth_platform_name", "")).strip()
    oauth_issuer_url = str(payload.get("oauth_issuer_url", "")).strip().rstrip("/")
    oauth_client_id = str(payload.get("oauth_client_id", "")).strip()
    oauth_redirect_uri = str(payload.get("oauth_redirect_uri", "")).strip()
    if oauth_provider not in {"", "github", "google", "microsoft", "custom"}:
        return jsonify(error="Select a supported OAuth provider."), 400
    if len(oauth_platform_name) > 150 or len(oauth_issuer_url) > 150 or len(oauth_client_id) > 150 or len(oauth_redirect_uri) > 150:
        return jsonify(error="OAuth values must be 150 characters or fewer."), 400
    if oauth_provider == "custom" and not oauth_platform_name:
        return jsonify(error="Enter a name for the Custom OIDC platform."), 400
    if oauth_provider == "custom" and not oauth_issuer_url:
        return jsonify(error="Enter an issuer URL for the Custom OIDC platform."), 400
    if oauth_issuer_url and not oauth_issuer_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return jsonify(error="OIDC issuer URL must use HTTPS or localhost."), 400
    if oauth_redirect_uri and not oauth_redirect_uri.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return jsonify(error="OAuth redirect URI must use HTTPS or localhost."), 400

    save_settings(keep_local, stream_responses, context_window_tokens)
    save_oauth_settings(
        oauth_provider,
        oauth_platform_name if oauth_provider == "custom" else "",
        oauth_issuer_url if oauth_provider == "custom" else "",
        oauth_client_id,
        oauth_redirect_uri,
    )
    return jsonify(message="Settings saved.", settings=get_settings(), context_window_tokens=get_context_window_tokens())

@app.route("/api/test-connection", methods=["POST"])
@login_required
@csrf_protect
def test_connection():
    payload = request.get_json(silent=True) or {}
    base_url = str(payload.get("base_url", "")).strip().rstrip("/")
    if not base_url:
        return "Base URL is missing", 400
    
    try:
        response = requests.get(base_url + "/api/version", timeout=5)
        if response.status_code != 200:
            return jsonify(error="Connection failed"), 502
    except requests.RequestException:
        return jsonify(error="Connection failed"), 502

    version = response.json().get("version", "unknown")
    save_ollama_connection(base_url, version, get_current_user().id)

    return jsonify(message="Connection successful", base_url=base_url, version=version)
