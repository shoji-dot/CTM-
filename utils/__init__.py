from datetime import datetime
from zoneinfo import ZoneInfo


def now_jst():
    return datetime.now(ZoneInfo("Asia/Tokyo")).replace(tzinfo=None)
