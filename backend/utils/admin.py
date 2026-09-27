from fastapi import Depends, HTTPException

from utils.auth import get_current_user


def require_admin(user=Depends(get_current_user)):
    """검증된 사용자의 서버 관리 메타데이터로 관리자 권한을 확인한다."""
    metadata = getattr(user, "app_metadata", None)

    if not isinstance(metadata, dict) or metadata.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="관리자 권한이 필요합니다",
        )

    return user
