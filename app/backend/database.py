# Database configuration and connection setup for Simply eChat
import uuid
from datetime import datetime, timezone

from app import db

# Schemas
# Example schema for a users table
# CREATE TABLE users (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     username TEXT NOT NULL,
#     email TEXT NOT NULL,
#     password TEXT NOT NULL
# );

# Ollama Connection Schema
# CREATE TABLE ollama_connection (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     base_url TEXT NOT NULL,
#     version TEXT NOT NULL
# );

# Ollama Models Schema
# CREATE TABLE ollama_models (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     model_name TEXT NOT NULL,
#     version TEXT NOT NULL
# );

# Ollama Chats Schema
# CREATE TABLE ollama_chats (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     chat_id TEXT NOT NULL
# );

# Application Settings Schema
# CREATE TABLE app_settings (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     setting_name TEXT NOT NULL,
#     setting_value TEXT NOT NULL
# );

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True, index=True)
    password = db.Column(db.String(150), nullable=False)


class OidcIdentity(db.Model):
    __table_args__ = (db.UniqueConstraint("issuer", "subject", name="uq_oidc_identity_issuer_subject"),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    issuer = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    
class OllamaConnection(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    base_url = db.Column(db.String(150), nullable=False)
    version = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    selected_model = db.Column(db.String(150), nullable=True)
    
class OllamaModel(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    model_name = db.Column(db.String(150), nullable=False)
    version = db.Column(db.String(150), nullable=False)
    
class OllamaChat(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chat_id = db.Column(db.String(150), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_created = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    title = db.Column(db.String(150), nullable=False, default="New conversation")

class OllamaChatHistory(db.Model):
    __table_args__ = (db.Index("ix_ollama_chat_history_chat_date", "chat_id", "date_created"),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("ollama_chat.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_created = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    setting_name = db.Column(db.String(150), nullable=False, unique=True)
    setting_value = db.Column(db.String(150), nullable=False)

DEFAULT_SETTINGS = {
    "keep_conversations_local": "true",
    "stream_responses": "true",
}
DEFAULT_OAUTH_SETTINGS = {
    "oauth_provider": "",
    "oauth_platform_name": "",
    "oauth_issuer_url": "",
    "oauth_client_id": "",
    "oauth_redirect_uri": "",
}
DEFAULT_CONTEXT_WINDOW_TOKENS = 4096


def migrate_schema() -> None:
    connection_columns = {column["name"] for column in db.inspect(db.engine).get_columns("ollama_connection")}
    if "user_id" not in connection_columns:
        db.session.execute(db.text("ALTER TABLE ollama_connection ADD COLUMN user_id INTEGER"))
    if "selected_model" not in connection_columns:
        db.session.execute(db.text("ALTER TABLE ollama_connection ADD COLUMN selected_model VARCHAR(150)"))

    chat_columns = {column["name"] for column in db.inspect(db.engine).get_columns("ollama_chat")}
    if "date_created" not in chat_columns:
        db.session.execute(db.text("ALTER TABLE ollama_chat ADD COLUMN date_created DATETIME"))
    if "title" not in chat_columns:
        db.session.execute(db.text("ALTER TABLE ollama_chat ADD COLUMN title VARCHAR(150) DEFAULT 'New conversation'"))
    db.session.commit()


def initialize_defaults() -> None:
    for name, value in {**DEFAULT_SETTINGS, **DEFAULT_OAUTH_SETTINGS}.items():
        if AppSetting.query.filter_by(setting_name=name).first() is None:
            db.session.add(AppSetting(setting_name=name, setting_value=value))
    db.session.commit()


def get_settings() -> dict[str, bool]:
    stored_settings = {
        setting.setting_name: setting.setting_value
        for setting in AppSetting.query.all()
    }
    return {
        name: stored_settings.get(name, default) == "true"
        for name, default in DEFAULT_SETTINGS.items()
    }


def get_context_window_tokens() -> int:
    setting = AppSetting.query.filter_by(setting_name="context_window_tokens").first()
    try:
        value = int(setting.setting_value) if setting else DEFAULT_CONTEXT_WINDOW_TOKENS
    except ValueError:
        value = DEFAULT_CONTEXT_WINDOW_TOKENS
    return min(max(value, 1024), 32768)


def save_settings(
    keep_conversations_local: bool,
    stream_responses: bool,
    context_window_tokens: int,
) -> None:
    settings = {
        "keep_conversations_local": keep_conversations_local,
        "stream_responses": stream_responses,
        "context_window_tokens": context_window_tokens,
    }
    for name, value in settings.items():
        setting = AppSetting.query.filter_by(setting_name=name).first()
        if setting is None:
            setting = AppSetting(setting_name=name, setting_value=str(value).lower())
            db.session.add(setting)
        else:
            setting.setting_value = str(value).lower()
    db.session.commit()


def get_oauth_settings() -> dict[str, str]:
    stored_settings = {
        setting.setting_name: setting.setting_value
        for setting in AppSetting.query.filter(AppSetting.setting_name.in_(DEFAULT_OAUTH_SETTINGS)).all()
    }
    return {
        name: stored_settings.get(name, default)
        for name, default in DEFAULT_OAUTH_SETTINGS.items()
    }


def save_oauth_settings(
    provider: str,
    platform_name: str,
    issuer_url: str,
    client_id: str,
    redirect_uri: str,
) -> None:
    settings = {
        "oauth_provider": provider,
        "oauth_platform_name": platform_name,
        "oauth_issuer_url": issuer_url,
        "oauth_client_id": client_id,
        "oauth_redirect_uri": redirect_uri,
    }
    for name, value in settings.items():
        setting = AppSetting.query.filter_by(setting_name=name).first()
        if setting is None:
            db.session.add(AppSetting(setting_name=name, setting_value=value))
        else:
            setting.setting_value = value
    db.session.commit()


def get_ollama_connection(user_id: int | None = None) -> OllamaConnection | None:
    query = OllamaConnection.query.order_by(OllamaConnection.id.desc())
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    return query.first()


def save_ollama_connection(
    base_url: str,
    version: str,
    user_id: int,
    selected_model: str | None = None,
) -> OllamaConnection:
    connection = get_ollama_connection(user_id)
    if connection is None:
        connection = OllamaConnection(
            base_url=base_url,
            version=version,
            user_id=user_id,
            selected_model=selected_model,
        )
        db.session.add(connection)
    else:
        connection.base_url = base_url
        connection.version = version
        if selected_model is not None:
            connection.selected_model = selected_model
    db.session.commit()
    return connection


def save_selected_model(user_id: int, model_name: str | None) -> OllamaConnection | None:
    connection = get_ollama_connection(user_id)
    if connection is None:
        return None
    connection.selected_model = model_name
    db.session.commit()
    return connection


def create_chat(user_id: int) -> OllamaChat:
    chat = OllamaChat(chat_id=uuid.uuid4().hex, user_id=user_id)
    db.session.add(chat)
    db.session.commit()
    return chat


def get_user_chats(user_id: int) -> list[OllamaChat]:
    return OllamaChat.query.filter_by(user_id=user_id).order_by(OllamaChat.date_created.desc()).all()


def get_user_chat(chat_id: str, user_id: int) -> OllamaChat | None:
    return OllamaChat.query.filter_by(chat_id=chat_id, user_id=user_id).first()


def set_chat_title_from_prompt(chat: OllamaChat, prompt: str) -> OllamaChat:
    if chat.title == "New conversation":
        words = prompt.split()
        chat.title = " ".join(words[:5]) or "New conversation"
        db.session.commit()
    return chat


def add_chat_message(chat: OllamaChat, role: str, content: str) -> OllamaChatHistory:
    message = OllamaChatHistory(chat_id=chat.id, role=role, content=content)
    db.session.add(message)
    db.session.commit()
    return message


def get_chat_messages(chat: OllamaChat) -> list[OllamaChatHistory]:
    return OllamaChatHistory.query.filter_by(chat_id=chat.id).order_by(OllamaChatHistory.date_created.asc()).all()


def build_chat_context(
    chat: OllamaChat,
    context_window_tokens: int,
    response_reserve_tokens: int = 512,
    max_messages: int = 200,
) -> tuple[list[dict[str, str]], int]:
    message_budget = max(1, context_window_tokens - response_reserve_tokens)
    recent_messages = (
        OllamaChatHistory.query.filter_by(chat_id=chat.id)
        .order_by(OllamaChatHistory.date_created.desc(), OllamaChatHistory.id.desc())
        .limit(max_messages)
        .all()
    )

    selected_messages = []
    used_tokens = 0
    for message in recent_messages:
        estimated_tokens = max(1, (len(message.content) + 3) // 4) + 4
        if selected_messages and used_tokens + estimated_tokens > message_budget:
            break
        selected_messages.append(message)
        used_tokens += estimated_tokens

    selected_messages.reverse()
    return [
        {"role": message.role, "content": message.content}
        for message in selected_messages
    ], used_tokens
