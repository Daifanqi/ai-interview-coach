"""
AI Interview System -- Core Data Structure Definitions: User Account

Week 14 (docs/decision_log.md decision #39/#43): the minimal user-identity
structure needed so InterviewSession.user_id can stop being permanently ""
(see backend/storage/db.py's list_sessions_by_user() docstring, and decision
#42's cross-session history_trend, which only becomes meaningful once real
user_id values exist).

Deliberately NOT modeling anything beyond username/password auth -- no
profile fields, no email, no OAuth identity, no "remember me" token -- per
decision #43's scope choice: this is a solo-practice-tool login gate, not a
production account system. Login state itself lives only in Streamlit's
st.session_state (see frontend/app.py) and does not survive a browser
refresh -- also decision #43, chosen specifically to avoid adding a cookie-
management dependency for this project's scope.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class User:
    """
    One registered account.

    password_hash is never the raw password -- see
    backend/storage/user_db.py's hashing helpers, the only place a raw
    password value should ever exist in memory (and only transiently, for
    the duration of a create_user()/authenticate_user() call).
    """

    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    password_hash: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
