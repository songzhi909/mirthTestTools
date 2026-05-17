# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Mirth Connect 消息追踪与调试工具集。用于排查 HIS、检查系统、PACS 等医疗信息系统间的消息推送问题。

## Database: `mirth_data`

Mirth Connect 的消息存储数据库，核心表命名规则：

| 表名模式 | 含义 | 示例 |
|----------|------|------|
| `d_mc{channel_id}` | 消息内容表 (Message Content) | `d_mc81`, `d_mc82`, `d_mc338` |
| `d_m{channel_id}` | 消息主表 (Message) | `d_m81`, `d_m82`, `d_m338` |
| `d_mm{channel_id}` | 消息状态/元数据表 (Message Metadata) | `d_mm81`, `d_mm82`, `d_mm338` |

### Content Type 枚举

| content_type | 含义 |
|-------------|------|
| 1 | RAW — 原始报文 |
| 9 | 错误堆栈 |
| 10 | Channel 变量 (编码后) |
| 11 | 响应报文 (Response) |

### Message Status 枚举

| STATUS | 含义 |
|--------|------|
| `S` | 成功 (SENT) |
| `T` | 已转换 (TRANSFORMED) |
| `R` | 已接收 (RECEIVED) |
| `E` | 错误 (ERROR) |

## Channel ID 映射

| Channel ID | 名称 | 用途 |
|-----------|------|------|
| 81 | HIS消息推送 | HIS 发送检查申请 (TJ001) |
| 82 | TJ001_V3 | V3 格式生成 |
| 111 | US_Sender | 超声推送 PACS |
| 138 | PIS_Sender | 病理推送 PACS |
| 157 | ES_Sender | 内镜推送 PACS |
| 169 | ECG_Sender | 心电推送 PACS |
| 173 | PACS_Sender | 通用 PACS 推送 |
| 338 | PACS_LY_Sender | PACS LY 推送 |
| 387 | OS_Sender | 其他推送 PACS |

Channel UUID 对照见表：

```
bd804290-6ab0-42a7-8d9a-4f7800ce9a86 | ECG_Sender        | 169
1fca6239-08fc-4a49-8f91-fbebd6de0df2 | ES_Sender         | 157
5622091b-de50-490a-9c8d-5626bd604f13 | OS_Sender         | 387
523b42d9-cd55-4e36-8d89-c432dd850812 | PACS_LY_Sender    | 338
be0cc595-2a43-4167-97f6-5b19cbe3217e | PACS_Sender       | 173
d96567d1-ab7a-45f0-a170-bd0d93b52d82 | PIS_Sender        | 138
d74bd209-b93e-4c95-8112-3e80c4328289 | US_Sender         | 111
```

## SQL 查询模式

### 排查消息的标准三步法

对任意业务场景，按以下三步排查：

**1. 消息发送** — 确认消息是否已发出

```sql
SELECT m.id, m.RECEIVED_DATE, mc.content
FROM mirth_data.d_mc{CH} mc
JOIN mirth_data.d_m{CH} m ON mc.message_id = m.id
WHERE m.RECEIVED_DATE > '{时间}'
  AND mc.content LIKE '%{关键字}%'
  AND mc.content_type = 1
ORDER BY m.id DESC;
```

**2. 是否成功** — 查看各 connector 的状态

```sql
SELECT mm.MESSAGE_ID, mm.CONNECTOR_NAME, mm.STATUS, mm.SEND_ATTEMPTS
FROM mirth_data.d_mm{CH} mm
JOIN mirth_data.d_mc{CH} mc ON mm.MESSAGE_ID = mc.message_id
WHERE mm.RECEIVED_DATE > '{时间}'
  AND mc.content_type = 1
  AND mc.content LIKE '%{关键字}%'
ORDER BY mm.MESSAGE_ID DESC;
```

**3. 错误查看** — 获取错误堆栈 (content_type = 9)

```sql
SELECT mc.message_id, mc.content
FROM mirth_data.d_mc{CH} mc
WHERE mc.message_id IN (
    SELECT message_id FROM mirth_data.d_mc{CH} WHERE content LIKE '%{关键字}%'
)
AND mc.content_type = 9;
```

### 带响应报文的查询

响应报文存储在 content_type = 10 或 11 的记录中，需要通过子查询提取并还原转义字符：

```sql
SELECT m.id, m.RECEIVED_DATE, mc.content,
    (SELECT REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        SUBSTRING_INDEX(SUBSTRING_INDEX(var_mc.content, '{变量名}</string>', -1), '</string>', 1),
        '<string>', ''), '&lt;', '<'), '&gt;', '>'), '&quot;', '"'), '&apos;', "'")
     FROM mirth_data.d_mc{CH} var_mc
     WHERE var_mc.message_id = m.id AND var_mc.content_type = {10|11}
     LIMIT 1) AS '响应报文'
FROM mirth_data.d_mc{CH} mc
JOIN mirth_data.d_m{CH} m ON mc.message_id = m.id
WHERE mc.content_type = 1 AND mc.content LIKE '%{关键字}%'
  AND m.RECEIVED_DATE > '{时间}'
ORDER BY m.id DESC;
```

### Channel 变量查询

直接从 content_type = 10 的记录中提取指定变量：

```sql
SELECT message_id,
    REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(content, '{变量名}</string>', -1), '</string>', 1), '<string>', '') AS '{别名}'
FROM mirth_data.d_mc{CH} WHERE message_id = '{消息ID}' AND CONTENT_TYPE = 10;
```

## 性能要点

- 查询必须加时间范围 (`m.RECEIVED_DATE > ...`)，否则全表扫描
- 先用 `content_type = 1` 过滤原始报文，可减少 50%+ 数据量
- 用 `EXAM_NO`、`apply_no` 等业务单号作为关键字定位消息

## 业务流程

```
HIS (TJ001) --[ch81]--> TJ001_V3 生成 --[ch82]--> PACS 推送 --[ch173/338/...]--> PACS 系统
```

排查时按链路顺序逐段检查：HIS发送 → V3生成 → PACS推送。

## GUI 工具

### 项目结构

```
├── app.py               # 主入口 + tkinter GUI
├── db.py                # 数据库连接层（从 config.ini 读取配置）
├── queries.py           # SQL 模板
├── config.ini           # 数据库连接配置
├── message_types.json   # 消息类型定义（可扩展）
```

### 运行

```bash
pip install pymysql
python app.py
```

### 扩展消息类型

编辑 `message_types.json`，新增条目即可，无需改代码。格式：

```json
{
  "消息类型名称": {
    "code": "业务代码",
    "keyword_field": "查询字段名",
    "keyword_tag": "XML标签名",
    "channels": {
      "通道名称": {
        "id": channel_id,
        "table_suffix": "表后缀",
        "response_var": "响应变量名(可选)",
        "response_content_type": 10
      }
    }
  }
}
```
