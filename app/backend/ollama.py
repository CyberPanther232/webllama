import re

import requests
from .database import get_ollama_connection
from openai import OpenAI


class OllamaRequestError(Exception):
    pass


MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


def _validate_model_name(model_name: str) -> str:
    model_name = model_name.strip()
    if not MODEL_NAME_PATTERN.fullmatch(model_name):
        raise OllamaRequestError("Enter a valid Ollama model name.")
    return model_name


def list_ollama_models(base_url: str) -> list[dict]:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=10)
        response.raise_for_status()
        return response.json().get("models", [])
    except requests.RequestException as error:
        raise OllamaRequestError("Could not list models from Ollama.") from error


def pull_ollama_model(base_url: str, model_name: str) -> None:
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/pull",
            json={"name": _validate_model_name(model_name), "stream": False},
            timeout=600,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise OllamaRequestError("Could not pull the requested model.") from error


def delete_ollama_model(base_url: str, model_name: str) -> None:
    try:
        response = requests.delete(
            f"{base_url.rstrip('/')}/api/delete",
            json={"name": _validate_model_name(model_name)},
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise OllamaRequestError("Could not delete the requested model.") from error

def get_connection_info() -> str | None:
    connection = get_ollama_connection()
    return connection.base_url if connection else None

def test_api_connection(base_url: str) -> bool:
    if not base_url:
        return False
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/version", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def generate_chat_response(
    base_url: str,
    messages: list[dict[str, str]],
    context_window_tokens: int,
    selected_model: str | None = None,
) -> tuple[str, str]:
    try:
        base_url = base_url.rstrip("/")
        models = list_ollama_models(base_url)
        if not models:
            raise OllamaRequestError("No Ollama models are installed.")

        installed_models = {model.get("name") for model in models}
        model_name = selected_model or models[0].get("name")
        if model_name not in installed_models:
            raise OllamaRequestError("The selected model is not installed.")
        if not model_name:
            raise OllamaRequestError("Ollama did not return a usable model.")

        response = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model_name,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": context_window_tokens, "num_predict": 512},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "").strip()
        
        # Save prompt and response to database
        
        
        if not content:
            raise OllamaRequestError("Ollama returned an empty response.")
        return content, model_name
    except requests.RequestException as error:
        raise OllamaRequestError("Could not get a response from Ollama.") from error

def create_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)

def generate_api_key() -> str:
    import secrets
    return secrets.token_hex(32)

def save_api_key(database_path: str, api_key: str) -> bool:
    try:
        conn = get_db_connection(database_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ollama_connection (api_key) VALUES (?)", (api_key,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving API key: {e}")
        return False
    return True

def generate_chat_id() -> str:
    import uuid
    return str(uuid.uuid4())

def save_chat_id(database_path: str, chat_id: str) -> bool:
    try:
        conn = get_db_connection(database_path)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ollama_chats (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving chat ID: {e}")
        return False
    return True

def list_chats(database_path: str) -> list:
    try:
        conn = get_db_connection(database_path)
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM ollama_chats")
        result = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"Error listing chats: {e}")
        result = []
    return [row[0] for row in result]

def delete_chat(database_path: str, chat_id: str) -> bool:
    try:
        conn = get_db_connection(database_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ollama_chats WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error deleting chat: {e}")
        return False
    return True

def get_chat(database_path: str, chat_id: str) -> dict:
    try:
        conn = get_db_connection(database_path)
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM ollama_chats WHERE chat_id = ?", (chat_id,))
        result = cursor.fetchone()
        conn.close()
    except Exception as e:
        print(f"Error getting chat: {e}")
        result = None
    return {"chat_id": result[0]} if result else None

def generate_connection_id() -> str:
    import uuid
    return str(uuid.uuid4())

