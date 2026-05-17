from __future__ import annotations

import json
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk, messagebox, scrolledtext
from typing import Dict, List, Optional

import db
import logger
import queries
import xml_parser


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = _get_base_dir()
MESSAGE_TYPES_PATH = BASE_DIR / "message_types.json"

TIME_RANGES = {
    "最近1小时": timedelta(hours=1),
    "最近6小时": timedelta(hours=6),
    "最近24小时": timedelta(hours=24),
    "最近3天": timedelta(days=3),
    "最近7天": timedelta(days=7),
}

STATUS_COLORS = {
    "success": "#4CAF50",
    "error": "#F44336",
    "empty": "#9E9E9E",
    "loading": "#FFC107",
}


def load_message_types() -> dict:
    with open(MESSAGE_TYPES_PATH, encoding="utf-8") as f:
        return json.load(f)


class FlowPanel(tk.Frame):
    """单个流程节点面板"""

    def __init__(self, master, channel_name: str, on_click, **kwargs):
        super().__init__(master, relief=tk.RAISED, borderwidth=2, **kwargs)
        self.channel_name = channel_name
        self.on_click = on_click
        self.status = "empty"
        self.has_input = False
        self.has_output = False

        self.configure(bg="#F5F5F5")
        self._build_ui()
        self.bind("<Button-1>", self._handle_click)

    def _build_ui(self):
        self.name_label = tk.Label(self, text=self.channel_name, font=("微软雅黑", 10, "bold"),
                                    bg="#F5F5F5", wraplength=140)
        self.name_label.pack(pady=(10, 4))
        self.name_label.bind("<Button-1>", self._handle_click)

        self.input_label = tk.Label(self, text="输入: -", font=("微软雅黑", 9), bg="#F5F5F5")
        self.input_label.pack(pady=2)
        self.input_label.bind("<Button-1>", self._handle_click)

        self.output_label = tk.Label(self, text="输出: -", font=("微软雅黑", 9), bg="#F5F5F5")
        self.output_label.pack(pady=2)
        self.output_label.bind("<Button-1>", self._handle_click)

        self.status_label = tk.Label(self, text="状态: 无数据", font=("微软雅黑", 9), bg="#F5F5F5")
        self.status_label.pack(pady=(4, 10))
        self.status_label.bind("<Button-1>", self._handle_click)

    def _handle_click(self, event):
        self.on_click(self.channel_name)

    def update_status(self, has_input: bool, has_output: bool, status: str):
        self.has_input = has_input
        self.has_output = has_output
        self.status = status

        input_text = "输入: ✓" if has_input else "输入: ✗"
        output_text = "输出: ✓" if has_output else "输出: ✗"

        status_map = {
            "success": ("状态: 成功", STATUS_COLORS["success"]),
            "error": ("状态: 错误", STATUS_COLORS["error"]),
            "empty": ("状态: 无数据", STATUS_COLORS["empty"]),
            "loading": ("状态: 查询中...", STATUS_COLORS["loading"]),
        }
        status_text, color = status_map.get(status, ("状态: 未知", "#666"))

        self.input_label.configure(text=input_text)
        self.output_label.configure(text=output_text)
        self.status_label.configure(text=status_text, fg=color)

        bg = "#E8F5E9" if status == "success" else "#FFEBEE" if status == "error" else "#F5F5F5"
        self.configure(bg=bg)
        for widget in [self.name_label, self.input_label, self.output_label, self.status_label]:
            widget.configure(bg=bg)


class ArrowLabel(tk.Label):
    """流程箭头"""

    def __init__(self, master, **kwargs):
        super().__init__(master, text="→", font=("微软雅黑", 16), fg="#666", **kwargs)


class MirthTestApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Mirth 消息追踪工具")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 650)

        self.msg_types = load_message_types()
        self.flow_panels: Dict[str, FlowPanel] = {}
        self._current_results: Dict[str, dict] = {}

        self._build_ui()

    # ── UI 构建 ──────────────────────────────────────────────

    def _build_ui(self):
        self._build_toolbar()
        self._build_flow_area()
        self._build_detail_area()
        self._build_statusbar()

    def _build_toolbar(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.X)

        ttk.Label(frame, text="消息类型:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.type_var = tk.StringVar()
        self.type_combo = ttk.Combobox(frame, textvariable=self.type_var,
                                        values=list(self.msg_types.keys()),
                                        state="readonly", width=14)
        self.type_combo.pack(side=tk.LEFT, padx=(4, 16))
        self.type_combo.current(0)
        self.type_combo.bind("<<ComboboxSelected>>", self._on_type_change)

        self.query_frame = ttk.Frame(frame)
        self.query_frame.pack(side=tk.LEFT)
        self.query_entries: Dict[str, ttk.Entry] = {}
        self._build_query_fields()

        ttk.Label(frame, text="时间:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=(16, 0))
        self.time_var = tk.StringVar(value="最近24小时")
        ttk.Combobox(frame, textvariable=self.time_var,
                      values=list(TIME_RANGES.keys()),
                      state="readonly", width=10).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Button(frame, text="查询", command=self._on_query).pack(side=tk.LEFT, padx=4)

    def _build_query_fields(self):
        for widget in self.query_frame.winfo_children():
            widget.destroy()
        self.query_entries.clear()

        type_name = self.type_var.get()
        mt = self.msg_types.get(type_name, {})
        fields = mt.get("query_fields", [])

        for i, field in enumerate(fields):
            label_text = field["label"]
            if field.get("required"):
                label_text += " *"
            ttk.Label(self.query_frame, text=label_text + ":", font=("微软雅黑", 10)).grid(
                row=0, column=i * 2, padx=(8 if i > 0 else 0, 2))
            entry = ttk.Entry(self.query_frame, width=16)
            entry.grid(row=0, column=i * 2 + 1, padx=(0, 4))
            self.query_entries[field["xml_tag"]] = entry

    def _build_flow_area(self):
        self.flow_frame = ttk.LabelFrame(self.root, text=" 消息流程 ", padding=16)
        self.flow_frame.pack(fill=tk.X, padx=10, pady=(4, 8))
        self._rebuild_flow_panels()

    def _rebuild_flow_panels(self):
        for w in self.flow_frame.winfo_children():
            w.destroy()
        self.flow_panels.clear()

        type_name = self.type_var.get()
        mt = self.msg_types.get(type_name, {})
        channels = mt.get("channels", [])

        if not channels:
            ttk.Label(self.flow_frame, text="该消息类型暂未配置通道流程",
                      font=("微软雅黑", 11), foreground="#999").pack(pady=20)
            return

        container = tk.Frame(self.flow_frame)
        container.pack()

        for i, ch in enumerate(channels):
            if i > 0:
                ArrowLabel(container).pack(side=tk.LEFT, padx=4)

            panel = FlowPanel(container, ch["name"], on_click=self._on_panel_click,
                              width=160, height=110)
            panel.pack(side=tk.LEFT, padx=4)
            panel.pack_propagate(False)
            self.flow_panels[ch["name"]] = panel

    def _build_detail_area(self):
        self.detail_frame = ttk.LabelFrame(self.root, text=" 详情 ", padding=8)
        self.detail_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))

        self.detail_notebook = ttk.Notebook(self.detail_frame)
        self.detail_notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_fields = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9))
        self.detail_notebook.add(self.tab_fields, text="字段解析")

        self.tab_input = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9))
        self.detail_notebook.add(self.tab_input, text="输入XML")

        self.tab_output = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9))
        self.detail_notebook.add(self.tab_output, text="输出XML")

        self.tab_vars = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9))
        self.detail_notebook.add(self.tab_vars, text="变量")

        self.tab_response = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9))
        self.detail_notebook.add(self.tab_response, text="响应")

        self.tab_error = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9))
        self.detail_notebook.add(self.tab_error, text="错误")

        self.tab_log = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9),
                                                  state="disabled")
        self.detail_notebook.add(self.tab_log, text="日志")

        # 初始化日志
        self._logger = logger.setup_logger(self.tab_log)
        self._logger.info("程序启动")

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN,
                  anchor=tk.W, padding=4).pack(fill=tk.X, side=tk.BOTTOM)

    # ── 事件处理 ──────────────────────────────────────────────

    def _on_type_change(self, _event=None):
        self._build_query_fields()
        self._rebuild_flow_panels()
        self._clear_detail()

    def _on_query(self):
        type_name = self.type_var.get()
        mt = self.msg_types.get(type_name, {})
        channels = mt.get("channels", [])
        fields = mt.get("query_fields", [])

        if not channels:
            messagebox.showinfo("提示", "该消息类型暂未配置通道")
            return

        keyword_parts = []
        for field in fields:
            tag = field["xml_tag"]
            entry = self.query_entries.get(tag)
            val = entry.get().strip() if entry else ""
            if field.get("required") and not val:
                messagebox.showwarning("提示", f"请输入{field['label']}")
                return
            if val:
                keyword_parts.append(val)

        if not keyword_parts:
            messagebox.showwarning("提示", "请输入至少一个查询条件")
            return

        keyword = keyword_parts[0]
        self._current_results.clear()
        self._clear_detail()

        self._logger.info("开始查询 - 类型: %s, 关键字: %s, 时间: %s", type_name, keyword, self.time_var.get())

        for panel in self.flow_panels.values():
            panel.update_status(False, False, "loading")

        self._set_status("查询中...")
        threading.Thread(target=self._do_query_all, args=(channels, keyword), daemon=True).start()

    def _on_panel_click(self, channel_name: str):
        result = self._current_results.get(channel_name)
        if not result:
            self._clear_detail()
            return

        self._show_detail(result)

    # ── 查询逻辑 ──────────────────────────────────────────────

    def _do_query_all(self, channels: list, keyword: str):
        time_str = self._get_time_str()
        self._logger.info("查询时间范围: %s", time_str)

        for i, ch in enumerate(channels):
            ch_id = ch["id"]
            ch_name = ch["name"]
            resp_var = ch.get("response_var")
            resp_ct = ch.get("response_content_type")
            self._logger.info("查询通道: %s (ID=%d)", ch_name, ch_id)

            result = {
                "channel_name": ch_name,
                "channel_id": ch_id,
                "input_xml": "",
                "output_xml": "",
                "variables": "",
                "response": "",
                "error": "",
                "has_input": False,
                "has_output": False,
                "status": "empty",
            }

            # 查询输入 XML (content_type = 1)
            try:
                sql = queries.sql_messages(ch_id, keyword, time_str)
                rows = db.execute_query(sql)
                if rows:
                    result["input_xml"] = rows[0].get("raw_content", "")
                    result["has_input"] = True
                    result["status"] = "success"
                    self._logger.info("通道 %s: 查询到 %d 条输入消息", ch_name, len(rows))
                else:
                    self._logger.info("通道 %s: 未查询到输入消息", ch_name)
            except Exception as e:
                result["error"] = f"查询输入失败: {e}"
                result["status"] = "error"
                self._logger.error("通道 %s 查询输入失败: %s", ch_name, e)

            # 查询输出 XML（下一环节的输入或本环节响应）
            if result["has_input"]:
                try:
                    if i + 1 < len(channels):
                        next_ch = channels[i + 1]
                        next_sql = queries.sql_messages(next_ch["id"], keyword, time_str)
                        next_rows = db.execute_query(next_sql)
                        if next_rows:
                            result["output_xml"] = next_rows[0].get("raw_content", "")
                            result["has_output"] = True
                    elif resp_var and resp_ct:
                        msg_id = str(rows[0].get("message_id", ""))
                        resp_sql = queries.sql_response(ch_id, msg_id, resp_var, resp_ct)
                        resp_rows = db.execute_query(resp_sql)
                        if resp_rows:
                            result["output_xml"] = resp_rows[0].get("var_value", "")
                            result["has_output"] = True
                except Exception as e:
                    result["error"] += f"\n查询输出失败: {e}"

            # 查询变量 (content_type = 10)
            if result["has_input"]:
                try:
                    msg_id = str(rows[0].get("message_id", ""))
                    vars_sql = queries.sql_variables(ch_id, msg_id)
                    vars_rows = db.execute_query(vars_sql)
                    if vars_rows:
                        result["variables"] = vars_rows[0].get("content", "")
                except Exception:
                    pass

            # 查询响应 (content_type = 11 或 response_var)
            if result["has_input"] and resp_var:
                try:
                    msg_id = str(rows[0].get("message_id", ""))
                    actual_ct = resp_ct if resp_ct else 11
                    resp_sql = queries.sql_response(ch_id, msg_id, resp_var, actual_ct)
                    resp_rows = db.execute_query(resp_sql)
                    if resp_rows:
                        result["response"] = resp_rows[0].get("var_value", "")
                except Exception:
                    pass

            # 查询错误 (content_type = 9)
            try:
                err_sql = queries.sql_error(ch_id, keyword)
                err_rows = db.execute_query(err_sql)
                if err_rows:
                    result["error"] = err_rows[0].get("error_detail", "")
                    result["status"] = "error"
            except Exception:
                pass

            self._current_results[ch_name] = result
            self.root.after(0, self._update_panel, ch_name, result)
            self._logger.info("通道 %s 查询完成 - 状态: %s, 输入: %s, 输出: %s",
                             ch_name, result["status"],
                             "有" if result["has_input"] else "无",
                             "有" if result["has_output"] else "无")

        self._logger.info("全部查询完成")
        self._set_status("查询完成")

    # ── UI 更新 ───────────────────────────────────────────────

    def _update_panel(self, ch_name: str, result: dict):
        panel = self.flow_panels.get(ch_name)
        if panel:
            panel.update_status(result["has_input"], result["has_output"], result["status"])

    def _show_detail(self, result: dict):
        # 字段解析
        type_name = self.type_var.get()
        mt = self.msg_types.get(type_name, {})
        extract_fields = mt.get("extract_fields", [])
        input_xml = result.get("input_xml", "")

        self.tab_fields.delete("1.0", tk.END)
        if extract_fields and input_xml:
            parsed = xml_parser.extract_fields(input_xml, extract_fields)
            self.tab_fields.insert(tk.END, xml_parser.format_extracted(parsed))
        elif input_xml:
            self.tab_fields.insert(tk.END, "(该消息类型未配置 extract_fields)")
        else:
            self.tab_fields.insert(tk.END, "(无输入报文)")

        self.tab_input.delete("1.0", tk.END)
        self.tab_input.insert(tk.END, input_xml)

        self.tab_output.delete("1.0", tk.END)
        self.tab_output.insert(tk.END, result.get("output_xml", ""))

        self.tab_vars.delete("1.0", tk.END)
        self.tab_vars.insert(tk.END, result.get("variables", ""))

        self.tab_response.delete("1.0", tk.END)
        self.tab_response.insert(tk.END, result.get("response", ""))

        self.tab_error.delete("1.0", tk.END)
        self.tab_error.insert(tk.END, result.get("error", ""))

        self.detail_frame.configure(text=f" 详情 - {result.get('channel_name', '')} ")

    def _clear_detail(self):
        for tab in [self.tab_fields, self.tab_input, self.tab_output, self.tab_vars, self.tab_response, self.tab_error]:
            tab.delete("1.0", tk.END)
        self.detail_frame.configure(text=" 详情 ")

    def _set_status(self, msg: str):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _get_time_str(self) -> str:
        delta = TIME_RANGES.get(self.time_var.get(), timedelta(hours=24))
        return (datetime.now() - delta).strftime("%Y-%m-%d %H:%M:%S")


def main():
    root = tk.Tk()
    MirthTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
