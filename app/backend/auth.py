
from functools import wraps
import hmac
import secrets
from urllib.parse import urlparse

from flask import flash, jsonify, redirect, request, session, url_for

from .. import bcrypt, db
from .database import OidcIdentity, User

def register_user(username: str, email: str, password: str) -> tuple[User | None, str | None]:
    username = username.strip()
    email = email.strip().lower()

    if not username or not email or not password:
        return None, "Name, email, and password are required."
    if "@" not in email:
        return None, "Enter a valid email address."
    if len(password) < 12:
        return None, "Password must be at least 12 characters."
    if User.query.filter_by(email=email).first() is not None:
        return None, "An account with that email already exists."

    user = User(
        username=username,
        email=email,
        password=bcrypt.generate_password_hash(password).decode("utf-8"),
    )
    db.session.add(user)
    db.session.commit()
    return user, None

def authenticate_user(email: str, password: str) -> User | None:
    user = User.query.filter_by(email=email.strip().lower()).first()
    if user is None or not bcrypt.check_password_hash(user.password, password):
        return None
    return user


def get_or_create_oidc_user(issuer: str, claims: dict) -> tuple[User | None, str | None]:
    subject = str(claims.get("sub", "")).strip()
    email = str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if not subject or "@" not in email:
        return None, "Your identity provider did not return a usable email address."
    if claims.get("email_verified") is False:
        return None, "Your identity provider has not verified this email address."

    identity = OidcIdentity.query.filter_by(issuer=issuer, subject=subject).first()
    if identity is not None:
        return db.session.get(User, identity.user_id), None

    existing_user = User.query.filter_by(email=email).first()
    if existing_user is not None:
        if claims.get("email_verified") is not True:
            return None, "Your identity provider must verify this email before it can be linked to an existing account."
        db.session.add(OidcIdentity(user_id=existing_user.id, issuer=issuer, subject=subject))
        db.session.commit()
        return existing_user, None

    username = str(claims.get("name") or claims.get("preferred_username") or email.split("@", 1)[0]).strip()[:150]
    user = User(
        username=username or "OIDC user",
        email=email,
        password=bcrypt.generate_password_hash(secrets.token_urlsafe(32)).decode("utf-8"),
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(OidcIdentity(user_id=user.id, issuer=issuer, subject=subject))
    db.session.commit()
    return user, None

def login_user(user: User) -> None:
    session.clear()
    session["user_id"] = user.id
    session.permanent = True

def logout_user() -> None:
    session.clear()

def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token

def csrf_protect(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return view(*args, **kwargs)
        supplied_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not hmac.compare_digest(supplied_token or "", get_csrf_token()):
            if request.path.startswith("/api/"):
                return jsonify(error="Invalid CSRF token."), 400
            flash("Your form expired. Please try again.")
            return redirect(request.url)
        return view(*args, **kwargs)
    return wrapped_view


def get_current_user() -> User | None:
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        return None
    return db.session.get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if get_current_user() is not None:
            return view(*args, **kwargs)
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify(error="Authentication required."), 401
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=next_url))
    return wrapped_view


def safe_next_url(next_url: str | None) -> str | None:
    if not next_url:
        return None
    parsed = urlparse(next_url)
    return next_url if not parsed.netloc and not parsed.scheme else None