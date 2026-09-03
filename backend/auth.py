"""
auth.py — Authentication utilities for the Web Admin Dashboard.

Handles:
- Admin credential verification (via secure config / environment)
- JWT token issuance and decoding
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import jwt

# Add root directory to path to import config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT token containing admin session claims."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=config.JWT_EXPIRATION_HOURS)
    )
    to_encode.update({"exp": expire, "sub": data.get("username", config.ADMIN_USERNAME)})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify a signed JWT token. Returns payload dict or None if invalid/expired."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def verify_admin_credentials(username: str, password: str) -> bool:
    """Verify provided credentials against configured admin credentials."""
    if not username or not password:
        return False
    return username.strip() == config.ADMIN_USERNAME and password.strip() == config.ADMIN_PASSWORD
