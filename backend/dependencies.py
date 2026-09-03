"""
dependencies.py — FastAPI dependencies for authentication and authorization.
"""
from typing import Dict, Any
from fastapi import Header, HTTPException, status, Depends
from backend.auth import verify_access_token


async def get_current_admin(authorization: str = Header(None)) -> Dict[str, Any]:
    """
    Extract and verify Bearer token from the Authorization header.
    Raises HTTP 401 if missing, invalid, or expired.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Use 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
