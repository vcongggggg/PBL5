import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.config_service import get_config_text

_DEFAULT_API_KEY = "pbl5_secure_key_12345"

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    api_key: Optional[str] = Depends(API_KEY_HEADER),
    db: Session = Depends(get_db),
):
    # Ưu tiên: ENV var → DB config → default fallback
    expected_key = (
        os.getenv("PARKING_API_SECRET_KEY", "").strip()
        or get_config_text(db, "api_secret_key", _DEFAULT_API_KEY)
    )
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing API Key",
        )
    return api_key
