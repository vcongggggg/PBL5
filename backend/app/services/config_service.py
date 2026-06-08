from sqlalchemy.orm import Session

from .. import models


def get_system_config_value(db: Session, key: str, default: float) -> float:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config:
        return default
    try:
        return float(config.value)
    except (TypeError, ValueError):
        return default


def get_config_text(db: Session, key: str, default: str = "") -> str:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config or not config.value:
        return default
    return str(config.value)


def set_config_text(db: Session, key: str, value: str) -> None:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if config:
        config.value = value
    else:
        db.add(models.SystemConfig(key=key, value=value))


def get_config_bool(db: Session, key: str, default: bool = False) -> bool:
    value = get_config_text(db, key, "1" if default else "0").strip().lower()
    return value in ["1", "true", "yes", "on", "enabled"]
