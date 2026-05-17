# Mirth 消息追踪工具

HIS、检查系统、PACS 等医疗信息系统间的消息推送追踪与调试工具，替代手动 SQL 查询，提升排障效率。

## 功能

- **消息流程可视化** — 按业务链路展示各环节的输入/输出/状态
- **HIS 数据预检** — 查询 Mirth 前自动校验 HIS 数据库（门诊缴费/住院校对等），异常时弹窗中止
- **多消息对比** — 同一通道多条消息可切换查看
- **字段解析** — 自动提取 XML 关键字段（检查申请号、检查类别等）
- **消息类别过滤** — 支持按消息类别筛选查询
- **查询进度** — 状态栏实时显示当前查询步骤

## 项目结构

```
├── app.py               # 主入口 + tkinter GUI
├── db.py                # MySQL 连接层（Mirth 消息库）
├── oracle_db.py         # Oracle 连接层（HIS 预检）
├── queries.py           # SQL 模板渲染
├── xml_parser.py        # XML 字段提取
├── logger.py            # 日志（文件 + GUI）
├── config.ini           # 数据库连接配置
├── message_types.json   # 消息类型定义（可扩展）
├── sql_templates.json   # SQL 模板（支持 {category} 变量）
├── MirthTools.spec       # PyInstaller 打包配置
```

## 安装与运行

```bash
pip install pymysql oracledb
python app.py
```

### 配置数据库连接

编辑 `config.ini`：

```ini
[database]
host = 192.168.254.34
port = 3306
user = mirth
password = Mirth123
database = mirth_data

[oracle]
host = 192.168.x.x
port = 1521
service_name = orcl
user = his_user
password = his_password
```

`[database]` 为 Mirth 消息库（MySQL），`[oracle]` 为 HIS 库（Oracle，可选，未配置则跳过预检）。

### 打包为 exe

```bash
pip install pyinstaller
# 编辑 MirthTools.spec 中的路径配置
pyinstaller MirthTools.spec
```

打包产物在 `dist/MirthTools.exe`，运行时需将 `config.ini`、`message_types.json`、`sql_templates.json` 放在 exe 同目录。

## 扩展消息类型

编辑 `message_types.json`，新增条目即可，无需改代码：

```json
{
  "消息类型名称": {
    "code": "业务代码",
    "query_fields": [
      {"label": "检查申请号", "xml_tag": "EXAM_NO", "required": true}
    ],
    "extract_fields": [
      {"label": "检查类别", "xpath": "ListInfo/ListRow/EXAM_APPOINTS/PriKeyList/EXAM_CLASS"}
    ],
    "channels": [
      {"name": "HIS消息推送", "id": 81, "table_suffix": "81"},
      {"name": "V3推送PACS", "id": 338, "table_suffix": "338",
       "response_var": "resp", "response_content_type": 11}
    ],
    "his_precheck": {
      "description": "HIS检查申请状态预检",
      "keyword_field": "EXAM_NO",
      "sql": "select ... from ... where t.exam_no = '{keyword}'",
      "status_field": "status",
      "fail_message_field": "status_name",
      "fields": [
        {"key": "type", "label": "就诊类型"},
        {"key": "status_name", "label": "状态"}
      ]
    }
  }
}
```

### his_precheck 配置说明

| 字段 | 说明 |
|------|------|
| `keyword_field` | 取哪个 query_fields 的值作为 SQL 的 `{keyword}` |
| `sql` | Oracle SQL 模板，`{keyword}` 为占位符 |
| `status_field` | 结果中表示状态的字段（"0"=失败，"1"=成功） |
| `fail_message_field` | 失败时取该字段值作为弹窗提示 |
| `fields` | 结果展示的列映射 |

## SQL 模板变量

`sql_templates.json` 中的 SQL 支持以下变量：

| 变量 | 说明 |
|------|------|
| `{channel_id}` | Mirth Channel ID |
| `{keyword}` | 查询关键字（业务单号） |
| `{time}` | 时间范围起点 |
| `{category}` | 消息类别（工具栏输入，可选） |

## 业务流程示例

```
HIS (TJ001) --[ch81]--> TJ001_V3 生成 --[ch82]--> PACS 推送 --[ch338]--> PACS 系统
```

## 依赖

- Python 3.7+
- pymysql — MySQL 连接
- oracledb — Oracle 连接（thick 模式，兼容 Oracle 11g）
- tkinter — GUI（Python 内置）
