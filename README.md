# Mirth 消息追踪工具

HIS、检查系统、PACS 等医疗信息系统间的消息推送追踪与调试工具，替代手动 SQL 查询，提升排障效率。

## 功能

- **消息流程可视化** — 按业务链路展示各环节的输入/输出/状态
- **HIS 数据预检** — 查询 Mirth 前自动校验 HIS 数据库（门诊缴费/住院校对等），异常时弹窗中止
- **Destinations 响应** — 查看下游系统返回的应答报文（content_type=6，按 metadata_id 区分目标端）
- **变量解析** — Channel 变量自动解析为键值对展示
- **条件通道路由** — 根据业务字段（如检查类别）自动选择推送通道
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
├── sql_templates.json   # SQL 模板
├── MirthTools.spec      # PyInstaller 打包配置
├── build.bat            # 一键打包脚本
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

双击运行 `build.bat` 即可一键打包，或手动执行：

```bash
buildenv\Scripts\python.exe -m PyInstaller MirthTools.spec
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
      {"name": "HIS消息推送", "id": 81, "table_suffix": "81", "use_category": true},
      {"name": "V3生成", "id": 82, "table_suffix": "82",
       "response_var": "tempPOOR_IN200901UV", "response_content_type": 10, "use_category": true},
      {
        "name": "推送", "conditional": true, "source_field": "exam_class", "default_index": 3,
        "options": [
          {"values": ["心电图"], "name": "ECG_Sender", "id": 169, "table_suffix": "169", "use_category": false},
          {"values": ["CT室", "放射科"], "name": "PACS_LY_Sender", "id": 338, "table_suffix": "338", "use_category": false}
        ]
      },
      {"name": "状态回写", "id": 225, "table_suffix": "225", "use_category": false, "dest_metadata_ids": [1]},
      {"name": "报告回写", "id": 18, "table_suffix": "18", "use_category": false, "dest_metadata_ids": [1]}
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

### channels 配置说明

| 字段 | 说明 |
|------|------|
| `name` | 通道显示名称 |
| `id` | Mirth Channel ID |
| `table_suffix` | 表名后缀（通常与 id 相同） |
| `use_category` | 是否启用消息类别过滤 |
| `response_var` | 响应变量名（可选，用于提取 channel 变量） |
| `response_content_type` | 响应内容类型（10=channel 变量，11=响应报文） |
| `dest_metadata_ids` | Destination 响应查询的 metadata_id 列表（可选） |

### 条件通道（conditional）

根据 HIS 预检返回的业务字段自动选择目标通道：

```json
{
  "name": "推送",
  "conditional": true,
  "source_field": "exam_class",
  "default_index": 3,
  "options": [
    {"values": ["心电图"], "name": "ECG_Sender", "id": 169, "table_suffix": "169"},
    {"values": ["CT室", "放射科"], "name": "PACS_LY_Sender", "id": 338, "table_suffix": "338"}
  ]
}
```

- `source_field`：从 HIS 预检结果中取哪个字段做匹配
- `default_index`：无匹配时使用 options 中的第几个（从 0 开始）
- `options.values`：匹配值列表

### Destinations 响应（dest_metadata_ids）

查看下游系统返回的应答报文（content_type=6）。`metadata_id` 标识目标端：

- `0` = Source（接收端）
- `1` = Destination 1（第一个目标发送端）
- `2` = Destination 2，以此类推

配置 `"dest_metadata_ids": [1]` 表示只查 Destination 1 的响应，`[1, 2]` 表示查 Destination 1 和 2。

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
| `{metadata_filter}` | Destination 响应过滤（由 dest_metadata_ids 自动生成） |

## 业务流程示例

### 检查申请（TJ001）

```
HIS --[ch81]--> V3生成 --[ch82]--> PACS推送 --[ch169/157/387/338/138/111]--> 状态回写[ch225] --> 报告回写[ch18]
```

### 检验申请（TJ021）

```
HIS --[ch81]--> V3生成 --[ch392]--> 推送[ch143]--> 状态回写[ch88] --> 报告回写[ch32]
```

## 依赖

- Python 3.7+
- pymysql — MySQL 连接
- oracledb — Oracle 连接（thick 模式，兼容 Oracle 11g）
- tkinter — GUI（Python 内置）
