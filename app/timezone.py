"""
タイムゾーンユーティリティ

全てのユーザー向けタイムスタンプをJST (Asia/Tokyo, UTC+9) で統一する。
datetime.utcnow() の代わりに jst_now() を使用すること。
"""
from datetime import datetime, timezone, timedelta

# JST (UTC+9) タイムゾーン
JST = timezone(timedelta(hours=9))


def jst_now() -> datetime:
    """現在時刻をJST (Asia/Tokyo) で返す"""
    return datetime.now(JST)
