from sqlalchemy.orm import Session

from .. import models
from .config_service import get_config_bool, set_config_text


def set_fire_alarm_active(db: Session, active: bool) -> None:
    set_config_text(db, "fire_alarm_active", "1" if active else "0")


def get_fire_alarm_active(db: Session) -> bool:
    return get_config_bool(db, "fire_alarm_active", False)


def is_fire_alarm_blocking(db: Session) -> bool:
    critical_count = (
        db.query(models.FireAlert)
        .filter(
            models.FireAlert.is_acknowledged == False,  # noqa: E712
            models.FireAlert.level == "critical",
        )
        .count()
    )
    return get_fire_alarm_active(db) or critical_count > 0


def resolve_open_fire_alerts(db: Session) -> int:
    count = (
        db.query(models.FireAlert)
        .filter(models.FireAlert.is_acknowledged == False)  # noqa: E712
        .update({models.FireAlert.is_acknowledged: True}, synchronize_session=False)
    )
    set_fire_alarm_active(db, False)
    db.commit()
    return int(count or 0)
