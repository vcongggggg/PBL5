import asyncio
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import models
from ..core.time_utils import get_vietnam_now
from ..database import SessionLocal


logger = logging.getLogger("uvicorn")


def cleanup_expired_pending_scans_once(db: Session, max_age_seconds: int = 120) -> int:
    cutoff = get_vietnam_now() - timedelta(seconds=max_age_seconds)
    deleted = db.query(models.PendingScan).filter(models.PendingScan.created_at < cutoff).delete()
    if deleted:
        db.commit()
    return deleted


async def cleanup_expired_pending_scans_loop():
    while True:
        try:
            await asyncio.sleep(60)
            db = SessionLocal()
            try:
                deleted = cleanup_expired_pending_scans_once(db)
                if deleted > 0:
                    logger.info(f"[CLEANUP] Đã tự động dọn dẹp {deleted} pending scans hết hạn.")
            except Exception as e:
                logger.error(f"[CLEANUP] Lỗi khi dọn dẹp pending scans: {e}")
                db.rollback()
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[CLEANUP] Lỗi ngoài dự kiến: {e}")
