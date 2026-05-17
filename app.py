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

try:
    import oracle_db
except ImportError:
    oracle_db = None


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

        ttk.Label(frame, text="类别:", font=("微软雅黑", 10)).pack(side=tk.LEFT, padx=(16, 0))
        self.category_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.category_var, width=10).pack(side=tk.LEFT, padx=(4, 16))

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

        self.tab_his = scrolledtext.ScrolledText(self.detail_notebook, wrap=tk.WORD, font=("Consolas", 9))
        self.detail_notebook.add(self.tab_his, text="HIS预检")

        # 初始化日志（仅写文件，不显示 tab）
        self._logger = logger.setup_logger(None)
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
        type_name = self.type_var.get()
        mt = self.msg_types.get(type_name, {})
        if not mt.get("his_precheck"):
            self.tab_his.delete("1.0", tk.END)
            self.tab_his.insert(tk.END, "该消息类型未配置HIS预检")

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

        category = self.category_var.get().strip()
        self._set_status("查询中...")
        threading.Thread(target=self._do_query_all, args=(channels, keyword, category), daemon=True).start()

    def _on_panel_click(self, channel_name: str):
        result = self._current_results.get(channel_name)
        if not result:
            self._clear_detail()
            return

        self._show_detail(result, channel_name)

    # ── 查询逻辑 ──────────────────────────────────────────────

    def _do_query_all(self, channels: list, keyword: str, category: str = ""):
        time_str = self._get_time_str()
        self._logger.info("查询时间范围: %s", time_str)

        type_name = self.type_var.get()
        mt = self.msg_types.get(type_name, {})
        his_config = mt.get("his_precheck")
        has_precheck = bool(his_config and oracle_db)
        total_steps = (1 if has_precheck else 0) + len(channels)
        step = 0

        # HIS 预检
        if has_precheck:
            step += 1
            self._set_status(f"[{step}/{total_steps}] HIS预检查询中...")
            self._logger.info("开始HIS预检查询...")
            try:
                his_sql = his_config["sql"].format(keyword=keyword)
                his_rows = oracle_db.execute_query(his_sql)
                his_result = {
                    "rows": his_rows,
                    "fields": his_config.get("fields", []),
                    "description": his_config.get("description", "HIS预检"),
                    "error": None,
                }
                self._current_results["_his_precheck"] = his_result
                self.root.after(0, self._update_his_tab, his_result)
                self._logger.info("HIS预检完成，返回 %d 条记录", len(his_rows))

                if not his_rows:
                    self._logger.warning("HIS预检: 未查到记录")
                    self.root.after(0, lambda: messagebox.showwarning("HIS预检", "HIS中未查到该申请单数据"))
                    self._set_status("HIS预检: 无数据")
                    return

                status_field = his_config.get("status_field", "status")
                fail_msg_field = his_config.get("fail_message_field", "status_name")
                if his_rows and str(his_rows[0].get(status_field, "1")) == "0":
                    fail_msg = his_rows[0].get(fail_msg_field, "HIS预检不通过")
                    self._logger.warning("HIS预检不通过: %s", fail_msg)
                    self.root.after(0, lambda m=fail_msg: messagebox.showwarning("HIS预检", m))
                    self._set_status("HIS预检不通过")
                    return
            except Exception as e:
                self._logger.error("HIS预检失败: %s", e)
                his_result = {"rows": [], "fields": [], "error": str(e)}
                self._current_results["_his_precheck"] = his_result
                self.root.after(0, self._update_his_tab, his_result)
                self.root.after(0, lambda m=str(e): messagebox.showwarning("HIS预检", f"HIS预检查询失败:\n{m}"))
                self._set_status("HIS预检失败")
                return
        elif his_config and not oracle_db:
            self._logger.warning("未安装 oracledb 模块，跳过HIS预检")

        for i, ch in enumerate(channels):
            step += 1
            ch_id = ch["id"]
            ch_name = ch["name"]
            self._set_status(f"[{step}/{total_steps}] 查询通道: {ch_name}...")
            resp_var = ch.get("response_var")
            resp_ct = ch.get("response_content_type")
            self._logger.info("查询通道: %s (ID=%d)", ch_name, ch_id)

            result = {
                "channel_name": ch_name,
                "channel_id": ch_id,
                "all_rows": [],
                "current_index": 0,
                "has_input": False,
                "has_output": False,
                "status": "empty",
                "next_ch_id": channels[i + 1]["id"] if i + 1 < len(channels) else None,
                "resp_var": resp_var,
                "resp_ct": resp_ct,
                "keyword": keyword,
                "time_str": time_str,
                "category": category,
            }

            # 查询输入 XML (content_type = 1)
            try:
                sql = queries.sql_messages(ch_id, keyword, time_str, category)
                rows = db.execute_query(sql)
                if rows:
                    result["all_rows"] = rows
                    result["has_input"] = True
                    result["status"] = "success"
                    self._logger.info("通道 %s: 查询到 %d 条输入消息", ch_name, len(rows))
                else:
                    self._logger.info("通道 %s: 未查询到输入消息", ch_name)
            except Exception as e:
                result["error"] = f"查询输入失败: {e}"
                result["status"] = "error"
                self._logger.error("通道 %s 查询输入失败: %s", ch_name, e)

            # 查询错误 (content_type = 9)
            try:
                err_sql = queries.sql_error(ch_id, keyword, category)
                err_rows = db.execute_query(err_sql)
                if err_rows:
                    result["error_detail"] = err_rows[0].get("error_detail", "")
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
            count = len(result.get("all_rows", []))
            panel.update_status(result["has_input"], result["has_output"], result["status"])
            if count > 0:
                panel.input_label.configure(text=f"输入: {count}条")

    def _update_his_tab(self, his_result: dict):
        self.tab_his.delete("1.0", tk.END)

        if his_result.get("error"):
            self.tab_his.insert(tk.END, f"HIS预检查询失败:\n{his_result['error']}\n\n")
            self.tab_his.insert(tk.END, "提示: 请检查 config.ini 中 [oracle] 配置是否正确\n")
            return

        rows = his_result.get("rows", [])
        fields = his_result.get("fields", [])

        if not rows:
            self.tab_his.insert(tk.END, "HIS预检: 未查到记录\n")
            return

        for i, row in enumerate(rows):
            if i > 0:
                self.tab_his.insert(tk.END, "\n" + "─" * 50 + "\n\n")
            self.tab_his.insert(tk.END, f"记录 {i + 1}:\n")
            for field in fields:
                key = field["key"]
                label = field["label"]
                value = row.get(key, "")
                if value is None:
                    value = ""
                self.tab_his.insert(tk.END, f"  {label:<12} : {value}\n")

    def _show_detail(self, result: dict, channel_name: str = ""):
        all_rows = result.get("all_rows", [])
        ch_id = result.get("channel_id", 0)
        error_detail = result.get("error_detail", "")

        self.detail_frame.configure(text=f" 详情 - {result.get('channel_name', channel_name)} ")

        if not all_rows:
            self._clear_detail()
            self.tab_fields.insert(tk.END, "(无输入报文)")
            if error_detail:
                self.tab_error.insert(tk.END, error_detail)
            return

        # 默认显示第一条消息
        self._show_message_detail(result, 0)

    def _show_message_detail(self, result: dict, index: int):
        all_rows = result.get("all_rows", [])
        ch_id = result.get("channel_id", 0)
        error_detail = result.get("error_detail", "")
        result["current_index"] = index

        type_name = self.type_var.get()
        mt = self.msg_types.get(type_name, {})
        extract_fields = mt.get("extract_fields", [])
        row = all_rows[index]
        input_xml = row.get("raw_content", "")
        msg_id = str(row.get("message_id", ""))

        # 字段解析 tab：顶部消息列表 + 下方字段解析
        self.tab_fields.delete("1.0", tk.END)
        if len(all_rows) > 1:
            self.tab_fields.insert(tk.END, f"共 {len(all_rows)} 条消息，点击切换:\n")
            self.tab_fields.insert(tk.END, "─" * 60 + "\n")
            list_start = self.tab_fields.index("end-1c")
            for i, r in enumerate(all_rows):
                date_str = str(r.get("received_date", ""))
                mid = r.get("message_id", "")
                marker = "▶" if i == index else " "
                self.tab_fields.insert(tk.END, f"{marker} [{i + 1}] {date_str}  ID={mid}\n")
            list_end = self.tab_fields.index("end-1c")
            self.tab_fields.insert(tk.END, "─" * 60 + "\n\n")
            # 绑定点击事件
            self.tab_fields.tag_configure("msg_list", foreground="#1565C0")
            self.tab_fields.tag_add("msg_list", list_start, list_end)
            self.tab_fields.tag_bind("msg_list", "<Button-1>",
                                     lambda e, r=result: self._on_message_list_click(e, r))
            self.tab_fields.configure(cursor="hand2")

        if extract_fields and input_xml:
            parsed = xml_parser.extract_fields(input_xml, extract_fields)
            self.tab_fields.insert(tk.END, xml_parser.format_extracted(parsed))
        elif input_xml:
            self.tab_fields.insert(tk.END, "(该消息类型未配置 extract_fields)")

        # 输入 XML
        self.tab_input.delete("1.0", tk.END)
        self.tab_input.insert(tk.END, input_xml)

        # 错误
        self.tab_error.delete("1.0", tk.END)
        if error_detail:
            self.tab_error.insert(tk.END, error_detail)

        # 懒加载：输出 XML、变量、响应
        self.tab_output.delete("1.0", tk.END)
        self.tab_output.insert(tk.END, "加载中...")
        self.tab_vars.delete("1.0", tk.END)
        self.tab_vars.insert(tk.END, "加载中...")
        self.tab_response.delete("1.0", tk.END)
        self.tab_response.insert(tk.END, "加载中...")

        threading.Thread(target=self._load_message_details,
                         args=(result, msg_id), daemon=True).start()

    def _on_message_list_click(self, event, result: dict):
        try:
            line = self.tab_fields.index(f"@{event.x},{event.y}").split(".")[0]
            all_rows = result.get("all_rows", [])
            # 第1行标题，第2行分隔线，第3行起是消息列表
            idx = int(line) - 3
            if 0 <= idx < len(all_rows):
                self._show_message_detail(result, idx)
        except (ValueError, IndexError):
            pass

    def _load_message_details(self, result: dict, msg_id: str):
        ch_id = result["channel_id"]
        next_ch_id = result.get("next_ch_id")
        resp_var = result.get("resp_var")
        resp_ct = result.get("resp_ct")
        keyword = result.get("keyword")
        time_str = result.get("time_str")
        category = result.get("category", "")

        output_xml = ""
        variables = ""
        response = ""

        self._set_status("加载消息详情...")
        try:
            if next_ch_id:
                next_sql = queries.sql_messages(next_ch_id, keyword, time_str, category)
                next_rows = db.execute_query(next_sql)
                if next_rows:
                    output_xml = next_rows[0].get("raw_content", "")
        except Exception:
            pass

        try:
            vars_sql = queries.sql_variables(ch_id, msg_id)
            vars_rows = db.execute_query(vars_sql)
            if vars_rows:
                variables = vars_rows[0].get("content", "")
        except Exception:
            pass

        if resp_var:
            try:
                actual_ct = resp_ct if resp_ct else 11
                resp_sql = queries.sql_response(ch_id, msg_id, resp_var, actual_ct)
                resp_rows = db.execute_query(resp_sql)
                if resp_rows:
                    response = resp_rows[0].get("var_value", "")
            except Exception:
                pass

        self.root.after(0, self._update_message_tabs, output_xml, variables, response)

    def _update_message_tabs(self, output_xml: str, variables: str, response: str):
        self.tab_output.delete("1.0", tk.END)
        self.tab_output.insert(tk.END, output_xml)
        self.tab_vars.delete("1.0", tk.END)
        self.tab_vars.insert(tk.END, variables)
        self.tab_response.delete("1.0", tk.END)
        self.tab_response.insert(tk.END, response)
        self._set_status("就绪")

    def _clear_detail(self):
        for tab in [self.tab_fields, self.tab_input, self.tab_output, self.tab_vars, self.tab_response, self.tab_error, self.tab_his]:
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
