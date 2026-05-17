from __future__ import annotations

import configparser
import sys
from pathlib import Path

from logger import get_logger


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


_config_path = _get_base_dir() / "config.ini"


def _load_config() -> dict | None:
    cfg = configparser.ConfigParser()
    cfg.read(_config_path, encoding="utf-8")
    if not cfg.has_section("oracle"):
        return None
    config = {
        "host": cfg.get("oracle", "host"),
        "port": cfg.getint("oracle", "port"),
        "service_name": cfg.get("oracle", "service_name"),
        "user": cfg.get("oracle", "user"),
        "password": cfg.get("oracle", "password"),
    }
    if cfg.has_option("oracle", "lib_dir"):
        config["lib_dir"] = cfg.get("oracle", "lib_dir")
    return config


_thick_initialized = False


def get_connection():
    import oracledb

    global _thick_initialized
    params = _load_config()
    if params is None:
        raise RuntimeError("未配置 Oracle 连接，请在 config.ini 中添加 [oracle] 配置段")
    if not _thick_initialized:
        if params.get("lib_dir"):
            lib_dir = params["lib_dir"]
        elif getattr(sys, "frozen", False):
            lib_dir = Path(sys._MEIPASS)
        else:
            lib_dir = _get_base_dir()
        oracledb.init_oracle_client(lib_dir=str(lib_dir))
        _thick_initialized = True
    log = get_logger()
    log.debug("连接Oracle %s@%s:%s/%s", params["user"], params["host"], params["port"], params["service_name"])
    return oracledb.connect(
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        service_name=params["service_name"],
    )


def execute_query(sql: str) -> list[dict]:
    log = get_logger()
    log.info("执行Oracle SQL: %s", sql)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [col[0].lower() for col in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            log.info("Oracle查询返回 %d 条记录", len(rows))
            return rows
    except Exception as e:
        log.error("Oracle SQL执行失败: %s", e)
        raise
    finally:
        conn.close()
