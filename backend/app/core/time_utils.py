from datetime import datetime, timedelta, timezone


ICT = timezone(timedelta(hours=7))


def get_vietnam_now() -> datetime:
    """Return current Vietnam time as a naive datetime."""
    return datetime.now(ICT).replace(tzinfo=None)


def get_vietnam_date():
    return datetime.now(ICT).date()
