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


def parse_variables_map(xml_str: str) -> list[dict]:
    """解析 <map><entry><string>key</string><string>value</string></entry>...</map> 格式。

    Returns:
        [{"key": "...", "value": "..."}]
    """
    if not xml_str:
        return []
    root = _parse_xml(xml_str)
    if root is None:
        return []
    results = []
    for entry in root.iter("entry"):
        strings = entry.findall("string")
        if len(strings) >= 2:
            key = strings[0].text or ""
            value = strings[1].text or ""
            results.append({"key": key.strip(), "value": value.strip()})
    return results


def format_variables(pairs: list[dict]) -> str:
    """将变量键值对格式化为可读文本。"""
    if not pairs:
        return ""
    max_key = max(len(p["key"]) for p in pairs) if pairs else 0
    lines = []
    for p in pairs:
        lines.append(f"{p['key']:<{max_key}} : {p['value']}")
    return "\n".join(lines)


def format_extracted(fields: list[dict]) -> str:
    """将提取结果格式化为可读文本。"""
    if not fields:
        return ""
    max_label = max(len(f["label"]) for f in fields)
    lines = []
    for f in fields:
        lines.append(f"{f['label']:<{max_label}} : {f['value']}")
    return "\n".join(lines)
