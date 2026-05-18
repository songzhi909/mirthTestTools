from __future__ import annotations

import configparser
import sys
import time
from pathlib import Path

import pymysql
import pymysql.cursors
from pymysql._auth import scramble_native_password

from logger import get_logger


def _load_slow_threshold() -> float:
    cfg = configparser.ConfigParser()
    cfg.read(_config_path, encoding="utf-8")
    try:
        return cfg.getfloat("settings", "slow_query_threshold", fallback=3.0)
    except (configparser.NoSectionError, ValueError):
        return 3.0


class _NativeAuthPlugin:
    """用 mysql_native_password 替代 caching_sha2_password，无需 cryptography 包。"""

    def __init__(self, conn):
        self._conn = conn

    def authenticate(self, pkt):
        data = scramble_native_password(self._conn.password, pkt.read_all())
        self._conn.write_packet(data)


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


_config_path = _get_base_dir() / "config.ini"


def _load_config() -> dict:
    cfg = configparser.ConfigParser()
    cfg.read(_config_path, encoding="utf-8")
    return {
        "host": cfg.get("database", "host"),
        "port": cfg.getint("database", "port"),
        "user": cfg.get("database", "user"),
        "password": cfg.get("database", "password"),
        "database": cfg.get("database", "database"),
    }


def get_connection():
    params = _load_config()
    log = get_logger()
    log.debug("连接数据库 %s@%s:%s/%s", params["user"], params["host"], params["port"], params["database"])
    return pymysql.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        database=params["database"],
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
        connect_timeout=5,
        auth_plugin_map={"caching_sha2_password": _NativeAuthPlugin},
    )


def execute_query(sql: str) -> list[dict]:
    log = get_logger()
    log.info("执行SQL: %s", sql)
    conn = get_connection()
    try:
        t0 = time.time()
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        elapsed = time.time() - t0
        threshold = _load_slow_threshold()
        if elapsed >= threshold:
            log.warning("⚠ SLOW SQL [%.2fs]: %s", elapsed, sql)
        else:
            log.info("查询返回 %d 条记录 (%.2fs)", len(rows), elapsed)
        return rows
    except Exception as e:
        log.error("SQL执行失败: %s", e)
        raise
    finally:
        conn.close()
