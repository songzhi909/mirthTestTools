from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict


def extract_fields(xml_str: str, fields: list[dict]) -> list[dict]:
    """从 XML 字符串中提取指定字段。

    Args:
        xml_str: XML 原始字符串
        fields: extract_fields 配置列表 [{"label": "...", "xpath": "..."}]

    Returns:
        [{"label": "...", "xpath": "...", "value": "..."}]
    """
    if not xml_str or not fields:
        return []

    root = _parse_xml(xml_str)
    if root is None:
        return []

    results = []
    for field in fields:
        label = field["label"]
        xpath = field["xpath"]
        value = _find_text(root, xpath)
        results.append({"label": label, "xpath": xpath, "value": value or ""})
    return results


def _parse_xml(xml_str: str) -> Optional[ET.Element]:
    """尝试解析 XML，自动处理 <xml> 前缀等情况。"""
    cleaned = xml_str.strip()
    # 移除 BOM
    if cleaned.startswith("﻿"):
        cleaned = cleaned[1:]
    # 尝试直接解析
    try:
        return ET.fromstring(cleaned)
    except ET.ParseError:
        pass
    # 尝试提取 <xml>...</xml> 内容
    match = re.search(r"<xml>(.*?)</xml>", cleaned, re.DOTALL)
    if match:
        try:
            return ET.fromstring(f"<xml>{match.group(1)}</xml>")
        except ET.ParseError:
            pass
    # 尝试提取第一个 XML 元素
    match = re.search(r"(<[a-zA-Z].*?>.*</[a-zA-Z].*?>)", cleaned, re.DOTALL)
    if match:
        try:
            return ET.fromstring(match.group(1))
        except ET.ParseError:
            pass
    return None


def _find_text(root: ET.Element, xpath: str) -> Optional[str]:
    """按 xpath 查找元素文本。支持 a/b/c 格式。"""
    elem = root.find(xpath)
    if elem is not None and elem.text:
        return elem.text.strip()
    # 尝试递归查找（忽略层级）
    tag = xpath.split("/")[-1]
    for child in root.iter(tag):
        if child.text and child.text.strip():
            return child.text.strip()
    return None


def format_extracted(fields: list[dict]) -> str:
    """将提取结果格式化为可读文本。"""
    if not fields:
        return ""
    max_label = max(len(f["label"]) for f in fields)
    lines = []
    for f in fields:
        lines.append(f"{f['label']:<{max_label}} : {f['value']}")
    return "\n".join(lines)
