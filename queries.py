from __future__ import annotations

import json
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _load_templates() -> dict:
    path = _get_base_dir() / "sql_templates.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_templates = _load_templates()


def _render(template_key: str, **kwargs) -> str:
    sql = _templates[template_key]["sql"]
    return sql.format(**kwargs)


def sql_messages(channel_id: int, keyword: str, time_str: str) -> str:
    return _render("messages", channel_id=channel_id, keyword=keyword, time=time_str)


def sql_messages_with_response(channel_id: int, keyword: str, time_str: str,
                                response_var: str, response_content_type: int) -> str:
    return _render("messages_with_response",
                    channel_id=channel_id, keyword=keyword, time=time_str,
                    response_var=response_var, response_content_type=response_content_type)


def sql_status(channel_id: int, keyword: str, time_str: str) -> str:
    return _render("status", channel_id=channel_id, keyword=keyword, time=time_str)


def sql_error(channel_id: int, keyword: str) -> str:
    return _render("error", channel_id=channel_id, keyword=keyword)


def sql_response(channel_id: int, message_id: str, var_name: str, content_type: int) -> str:
    return _render("response",
                    channel_id=channel_id, message_id=message_id,
                    var_name=var_name, content_type=content_type)


def sql_variables(channel_id: int, message_id: str) -> str:
    return _render("variables", channel_id=channel_id, message_id=message_id)
