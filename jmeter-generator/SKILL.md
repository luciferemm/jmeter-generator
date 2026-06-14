---
name: jmeter-generator
description: |
  根据用户提供的 API 接口信息和测试场景描述，自动生成可直接执行的 JMeter (.jmx) 脚本。
  支持从 input/ 文件夹批量解析接口文档（Markdown/JSON/YAML/OpenAPI/HAR），一键生成完整脚本到 output/ 文件夹。
  适用场景: "帮我生成 JMeter 脚本"、"为一个登录接口创建压测脚本"、"帮我写一个压测脚本"、"批量生成压测脚本"
---

# JMeter 脚本生成器

我负责将 API 接口信息和测试场景描述转化为可直接执行的 JMeter `.jmx` 脚本。目标 JMeter 版本：**5.x**。

## 路径约定

本 skill 中所有引用及运行脚本的路径优先从当前 skill 目录查找，例如：
- 引用 `references/jmeter_template.jmx`
- 运行脚本 `python scripts/jmx_builder.py --config config.json --output script.jmx`
- **用户接口文档** 放入 `input/` 文件夹
- **生成的 JMX 脚本** 输出到 `output/` 文件夹

## 目录结构

```
jmeter-generator/
├── SKILL.md                     # AI 驱动的 Skill 定义
├── config.json                  # 默认配置
├── pyproject.toml               # Python 项目配置
├── scripts/
│   ├── jmx_builder.py           # 核心构建脚本：将配置 JSON 转换为 .jmx 文件
│   ├── har_parser.py            # HAR 文件解析器
│   └── api_doc_parser.py        # 批量接口文档解析器（NEW）
├── references/
│   ├── jmeter_template.jmx      # JMX 模板参考
│   └── scenario_guide.md        # 测试场景描述编写指南
├── examples/
│   ├── demo_basic.md            # 完整对话流程示例
│   └── demo_output.jmx          # 生成结果示例
├── input/                       # 用户存放接口文档的文件夹（NEW）
│   ├── .gitkeep
│   └── example_api_doc.md       # 示例接口文档
├── output/                      # 生成的 JMX 脚本输出文件夹（NEW）
│   └── .gitkeep
└── README.md
```

## 核心工作流程

### 入口分支判断

用户请求生成 JMeter 脚本时，按以下优先级判断处理模式：

| 用户输入 | 处理模式 | 说明 |
|----------|----------|------|
| "批量生成"、"从 input 生成"、"解析接口文档" | **批量导入模式** | 扫描 input/ 文件夹，批量解析 |
| 提供了 HAR 文件路径 / `.har` 文件 | **HAR 导入模式** | 调用 har_parser.py 解析 |
| 手动描述接口信息 | **手动录入模式** | 逐条引导录入接口 |

---

### 模式一：批量导入模式（推荐）

用户将接口文档放入 `input/` 文件夹，一次性批量生成 JMeter 脚本到 `output/`。

**适用场景**：
- 用户已有接口文档（Markdown / JSON / YAML / OpenAPI / HAR）
- 需要一次性生成多个接口的测试脚本
- 不想逐条手动录入接口信息

**支持的文档格式**：

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| Markdown | `.md` | 结构化接口文档，支持多接口（见示例） |
| JSON | `.json` | 单个接口 / 接口数组 / 完整 ScriptConfig |
| YAML | `.yaml` / `.yml` | 同 JSON 结构 |
| OpenAPI / Swagger | `.json` / `.yaml` | 完整 OpenAPI 3.x 或 Swagger 2.x 规范 |
| HAR | `.har` | HTTP Archive 文件（自动委托 har_parser.py） |

**操作步骤**：

1. **确认文档位置**：询问用户接口文档是否已在 `input/` 中，或引导用户放入
2. **询问测试场景**：解析出接口列表后，询问用户测试场景（并发数、持续时间、断言等）
3. **预览摘要**：展示将要生成的脚本摘要
4. **执行生成**：运行以下命令，一键完成解析+生成：
   ```
   python scripts/api_doc_parser.py --input-dir input/ --output-dir output/ --generate
   ```
5. **输出结果**：告知用户 `output/` 中的 JMX 文件路径

**带场景参数的一键命令**：

如果用户已经描述了场景（如"100并发跑5分钟"），先创建 scenario.json 再生成：

```bash
# 第一步：创建场景配置
echo '{"threads":100,"ramp_up":30,"duration":300,"assertions":[{"type":"status_code","condition":"equals","expected":"200"},{"type":"response_time","condition":"less_than","expected":"2000"}]}' > input/_scenario.json

# 第二步：批量解析 + 生成
python scripts/api_doc_parser.py --input-dir input/ --output-dir output/ --generate --scenario input/_scenario.json --test-name "登录+用户信息压测"
```

**只解析不生成**（查看中间配置）：

```bash
python scripts/api_doc_parser.py --input-dir input/ --output-config input/_merged_config.json
```

**预览示例**：
```
==================================================
  [*] Found 2 API doc file(s) in input/
==================================================

  [>] Parsing: login_api.md  [markdown]
     OK Extracted 3 interface(s)

  [>] Parsing: user_api.yaml  [yaml]
     OK Extracted 5 interface(s)

==================================================
  --- Parse Summary ---
==================================================
  Total files scanned: 2
  Raw interfaces:      8
  Unique interfaces:   7
  Test name:           Auto Generated Test (7 APIs)
==================================================

  Interfaces:
    1. POST   HTTPS://api.example.com/login [body: 45 chars]
    2. GET    HTTPS://api.example.com/user/profile
    3. PUT    HTTPS://api.example.com/user/profile [body: 50 chars]
    ...

==================================================
  *** JMeter Script Generated! ***
==================================================
  File: output\Auto_Generated_Test_7_APIs_20260614_180219.jmx
  Size: 18,234 bytes
==================================================
```

---

### 模式二：HAR 导入模式

**HAR 导入流程**：

1. 用户提供 HAR 文件路径（或拖拽 HAR 文件到终端）
2. 询问是否启用动态参数检测（默认开启）、认证提取（默认开启）
3. 运行 `python scripts/har_parser.py --har <file> --output <temp_config.json>`
4. 展示解析摘要：

   ```
   📋 HAR 解析摘要
   ━━━━━━━━━━━━━━━━━━━━━
   HAR 版本: 1.2 | 条目数: 42
   去重后接口: 15 个
   动态参数检测: 时间戳(3处), UUID(1处)
   认证变量: auth_token, auth_cookie
   ━━━━━━━━━━━━━━━━━━━━━
   ```

5. 用户确认后，加载解析结果作为接口信息，进入阶段二

---

### 模式三：手动录入模式（原有流程）

**阶段一：收集接口信息**

1. **引导用户录入接口**：询问 Method、URL、Headers、Body
2. **组装数据结构**：将录入信息组装为 ApiInterface（见数据结构定义）
3. **多接口支持**：用户可录入多个接口，按顺序编号

**用户输入示例**：

```
POST https://api.example.com/login
Headers: Content-Type: application/json
Body: {"username":"test","password":"123456"}
```

**输出结构**：

```json
{
  "name": "登录接口",
  "method": "POST",
  "protocol": "HTTPS",
  "host": "api.example.com",
  "path": "/login",
  "headers": [{"name": "Content-Type", "value": "application/json"}],
  "body": {"type": "json", "content": "{\"username\":\"test\",\"password\":\"123456\"}"}
}
```

**阶段二：解析测试场景**

1. **接收自然语言描述**：用户描述测试意图
2. **关键词解析**：按解析规则表提取结构化参数
3. **歧义检测**：缺少关键参数时主动追问
4. **二次确认**：关键参数确认后生成 TestScenario

**用户输入示例**：

```
100 个并发跑 5 分钟，检查返回码 200，响应不超过 2 秒，提取 token
```

**解析结果**：

```json
{
  "threads": 100,
  "duration": 300,
  "ramp_up": 30,
  "assertions": [
    {"type": "status_code", "condition": "equals", "expected": "200"},
    {"type": "response_time", "condition": "less_than", "expected": "2000"}
  ],
  "variables": [
    {"name": "token", "source": "extractor", "expression": "$.token"}
  ]
}
```

**带 CSV 参数化示例**：

用户输入：*"100 并发，从 users.csv 读取用户名和密码，循环 1000 次，检查登录成功"*

解析结果：
```json
{
  "threads": 100,
  "loops": 1000,
  "csv_data": {"filename": "users.csv", "variableNames": "username,password"},
  "assertions": [
    {"type": "response_body", "condition": "contains", "expected": "success"}
  ]
}
```

**阶段三：生成 JMeter 脚本**

1. **预览摘要**：输出前展示脚本结构摘要（接口数、线程数、断言数、是否参数化）
2. **用户确认**：展示摘要后等待用户确认
3. **合并数据**：将 ApiInterface + TestScenario 组装为 ScriptConfig，写入临时 JSON
4. **调用构建脚本**：运行 `python scripts/jmx_builder.py --config <temp.json> --output <output.jmx>`
5. **输出结果**：告知用户文件路径，提示 `jmeter -n -t` 执行

**预览示例**：
```
📋 脚本预览
━━━━━━━━━━━━━━━━━━━━━
接口: 2 个 (POST /login, GET /user/profile)
线程: 100 并发 | 预热 30s | 持续 300s
断言: 状态码=200, 响应时间<2000ms
提取器: token ($.token)
参数化: data.csv (username, password)
监听器: Summary Report, View Results Tree
━━━━━━━━━━━━━━━━━━━━━
确认生成脚本？(y/n)
```

---

## 自然语言解析规则

| 用户表述 | 解析结果 |
|----------|----------|
| "N个并发"、"N线程"、"N users" | threads = N |
| "跑M分钟"、"持续M秒"、"duration M" | duration = M (秒) |
| "预热30秒"、"ramp-up 30" | ramp_up = 30 |
| "循环N次"、"loop N" | loops = N |
| "永远跑"、"持续跑" | loops = -1 |
| "检查返回码200"、"状态码200" | assertion: status_code = 200 |
| "响应不超过Ns"、"响应<Ns" | assertion: response_time < N*1000 |
| "检查xxx字段"、"验证yyy" | assertion: json_path = xxx |
| "提取token"、"拿到token" | variable: token, source=extractor, expression=$.token |
| "从data.csv读取"、"参数化" | csv_data: filename=data.csv |
| "检查返回体包含xxx" | assertion: response_body contains xxx |

## 歧义追问策略

| 场景 | 追问 |
|------|------|
| 未指定并发数 | "请问需要多少个并发用户？" |
| 未指定持续时间/循环次数 | "请问需要跑多久（如5分钟），或者循环多少次？" |
| 并发数 > 10000 | "并发超过 10000 可能会对目标服务器造成较大压力，确认继续吗？" |
| 未指定断言 | "需要检查哪些响应条件？如状态码、响应时间等" |
| Method 非标准 | "`{method}` 不是标准 HTTP Method，已默认转为 GET，需要修改吗？" |
| input/ 中有多个文档 | "发现了 N 个接口文档，是否全部解析？（y/n/选择性指定）" |
| 解析出的接口数为0 | "未能从文档中解析出接口，请检查格式。可参考 input/example_api_doc.md" |

## 数据模型

### ApiInterface

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | String | 是 | 接口名称 |
| method | String | 是 | GET/POST/PUT/DELETE/PATCH |
| protocol | String | 是 | HTTP/HTTPS |
| host | String | 是 | 主机地址 |
| port | Integer | 可选 | 端口，默认 80/443 |
| path | String | 是 | 接口路径 |
| headers | Array | 可选 | [{name, value}] |
| query_params | Array | 可选 | [{name, value}] |
| body | Object | 可选 | {type, content} |

### TestScenario

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| threads | Integer | 是 | 并发用户数 |
| ramp_up | Integer | 否 | 预热秒数, 默认 threads |
| duration | Integer | 否 | 持续秒数, 与 loops 互斥 |
| loops | Integer | 否 | 循环次数, -1=永远 |
| assertions | Array | 否 | 断言列表 |
| variables | Array | 否 | 变量列表 |
| csv_data | Object | 否 | {filename, variableNames, delimiter} |

### 新增配置：HarImportConfig

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| har_path | String | 是 | - | HAR 文件路径 |
| detect_dynamic | Boolean | 否 | true | 是否自动检测动态参数（时间戳/UUID） |
| extract_auth | Boolean | 否 | true | 是否提取认证信息为变量 |
| cookie_manager | Boolean | 否 | true | 是否自动添加 Cookie Manager |

## 快速决策树

### 用户提供了什么？

| 输入 | 处理方式 |
|------|----------|
| "批量生成" / "从 input 生成" | → 模式一：批量导入，扫描 input/ 文件夹 |
| 接口文档文件（.md/.json/.yaml） | → 引导放入 input/ 或直接指定文件路径 |
| 接口信息 | → 模式三：继续询问场景描述 |
| 测试场景描述 | → 模式三阶段二：如果已有接口信息则生成脚本 |
| 一体化的描述（含接口+场景） | → 模式三：分别解析 |
| "帮我写个压测脚本" | → 从零开始引导 |
| HAR 文件路径 / `.har` 文件 | → 模式二：HAR 导入模式，自动解析 |
| 拖拽 HAR 文件到终端 | → 模式二：识别为 HAR 导入模式，自动解析 |

### 当前状态

| 状态 | AI 行为 |
|------|---------|
| input/ 中有文档，用户说"批量生成" | 运行 api_doc_parser.py --generate |
| 已有接口信息，缺场景 | 追问场景描述 |
| 已有场景，缺接口 | 追问接口信息 |
| 两者都齐 | 进入脚本生成 |

## 如何使用脚本

### 批量导入生成（推荐）
- **一键生成**：`python scripts/api_doc_parser.py --input-dir input/ --output-dir output/ --generate`
- **只解析不生成**：`python scripts/api_doc_parser.py --input-dir input/ --output-config merged.json`
- **带场景参数**：`python scripts/api_doc_parser.py --input-dir input/ --output-dir output/ --generate --scenario scenario.json`
- **指定文件**：`python scripts/api_doc_parser.py --files api1.md api2.json --output-dir output/ --generate`

### 手动构建
- **生成 JMeter 脚本**：`python scripts/jmx_builder.py --config <config.json> --output <script.jmx>`
- **从 HAR 导入接口**：`python scripts/har_parser.py --har <session.har> --output <config.json>`
- **HAR 导入后生成脚本**：`python scripts/har_parser.py --har session.har --output temp.json && python scripts/jmx_builder.py --config temp.json --output script.jmx`

### 参考文档
- **查看 JMX 模板**：读取 `references/jmeter_template.jmx`
- **查看场景编写指南**：读取 `references/scenario_guide.md`
- **查看示例**：读取 `examples/demo_basic.md`
- **查看接口文档示例**：读取 `input/example_api_doc.md`

---

## 实施说明

执行本 skill 时，请按以下步骤操作：

### 批量导入模式（用户有接口文档时优先使用）

1. **确认 input/ 中有文档**：`ls input/` 查看
2. **运行批量解析**：`python scripts/api_doc_parser.py --input-dir input/ --output-config input/_merged_config.json`
3. **展示解析摘要**给用户，确认接口列表
4. **询问测试场景**：并发数、持续时间、断言等
5. **如用户提供场景**，写入 `input/_scenario.json`，用 `--scenario` 参数生成
6. **生成 JMX**：`python scripts/api_doc_parser.py --input-dir input/ --output-dir output/ --generate [--scenario input/_scenario.json] [--test-name "测试名称"]`
7. **输出结果**：告知 `output/` 中的文件路径，提示执行命令

### 手动录入模式

1. **读取 `references/jmeter_template.jmx`** 了解 JMX 基础结构
2. **按阶段一收集接口信息**，组装为 ApiInterface
3. **按阶段二解析场景**，按解析规则表提取参数，有歧义时追问
4. **展示脚本预览摘要**，等待用户确认
5. **合并为 ScriptConfig** 写入临时 JSON 文件
6. **调用 `python scripts/jmx_builder.py --config <temp.json> --output <output.jmx>`** 生成 .jmx
7. **输出结果**：告知文件路径（默认 `jmeter_<timestamp>.jmx`，用户可自定义），提示 `jmeter -n -t` 执行
