"""Authentication: password hashing and Streamlit session user."""

from __future__ import annotations

from typing import Optional

import bcrypt
import streamlit as st
from sqlalchemy.orm import Session, joinedload

from models import AppUser

SESSION_USER_ID = "pms_user_id"
SESSION_LAST_LOGIN_DISPLAY = "pms_last_login_display"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def attempt_login(session: Session, email: str, password: str) -> Optional[AppUser]:
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    user = (
        session.query(AppUser)
        .options(joinedload(AppUser.role), joinedload(AppUser.student))
        .filter(AppUser.email == email)
        .first()
    )
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password):
        return None
    return user


def set_session_from_user(user: AppUser) -> None:
    st.session_state[SESSION_USER_ID] = user.id


def clear_auth_session() -> None:
    st.session_state.pop(SESSION_USER_ID, None)
    st.session_state.pop(SESSION_LAST_LOGIN_DISPLAY, None)


def get_current_user(session: Session) -> Optional[AppUser]:
    uid = st.session_state.get(SESSION_USER_ID)
    if not uid:
        return None
    return (
        session.query(AppUser)
        .options(joinedload(AppUser.role), joinedload(AppUser.student))
        .filter_by(id=int(uid))
        .first()
    )


def is_logged_in() -> bool:
    return bool(st.session_state.get(SESSION_USER_ID))
