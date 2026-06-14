# JMeter Generator

根据用户提供的 API 接口信息和测试场景描述，自动生成可直接执行的 JMeter (`.jmx`) 脚本。支持 JMeter **5.x**。

## 目录结构

```
jmeter-generator/
├── SKILL.md                 # AI 驱动的 Skill 定义（供 opencode agent 使用）
├── config.json              # 默认配置（JMeter 版本、监听器等）
├── pyproject.toml           # Python 项目配置
├── scripts/
│   ├── jmx_builder.py       # 核心构建脚本：将配置 JSON 转换为 .jmx 文件
│   ├── har_parser.py        # HAR 文件解析器
│   └── api_doc_parser.py    # 批量接口文档解析器
├── references/
│   ├── jmeter_template.jmx  # JMX 模板参考
│   └── scenario_guide.md    # 测试场景描述编写指南
├── examples/
│   ├── demo_basic.md        # 完整对话流程示例
│   └── demo_output.jmx      # 生成结果示例
├── input/                   # 用户存放接口文档
│   ├── .gitkeep
│   └── example_api_doc.md   # 示例接口文档（Markdown 格式）
├── output/                  # 生成的 JMX 脚本输出
│   └── .gitkeep
└── README.md
```

## 快速开始

### 方式一：批量导入生成（推荐）

将接口文档放入 `input/` 文件夹，一键生成：

```bash
# 1. 将接口文档放入 input/ 文件夹
cp your_api_doc.md input/

# 2. 一键解析 + 生成 JMX 脚本
python scripts/api_doc_parser.py --input-dir input/ --output-dir output/ --generate

# 3. 生成的脚本在 output/ 文件夹中
ls output/
```

**带自定义场景参数**：

```bash
# 创建场景配置
cat > input/_scenario.json << EOF
{
  "threads": 100,
  "ramp_up": 30,
  "duration": 300,
  "assertions": [
    {"type": "status_code", "condition": "equals", "expected": "200"},
    {"type": "response_time", "condition": "less_than", "expected": "2000"}
  ]
}
EOF

# 使用场景配置生成
python scripts/api_doc_parser.py --input-dir input/ --output-dir output/ --generate \
    --scenario input/_scenario.json --test-name "登录压测"
```

### 方式二：HAR 文件导入

```bash
# 从浏览器 HAR 导出文件生成脚本
python scripts/har_parser.py --har session.har --output config.json
python scripts/jmx_builder.py --config config.json --output script.jmx
```

### 方式三：手动构建配置

```bash
# 直接传入配置 JSON 生成 JMX
python scripts/jmx_builder.py --config config.json --output script.jmx
```

## 支持的接口文档格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| Markdown | `.md` | 结构化接口文档，支持多接口 |
| JSON | `.json` | 单个接口 / 接口数组 / 完整 ScriptConfig |
| YAML | `.yaml` / `.yml` | 同 JSON 结构 |
| OpenAPI / Swagger | `.json` / `.yaml` | 完整 OpenAPI 3.x 或 Swagger 2.x 规范 |
| HAR | `.har` | HTTP Archive 文件 |

### Markdown 接口文档示例

```markdown
## 接口1：用户登录

- **Method**: POST
- **URL**: https://api.example.com/login
- **Headers**:
  - Content-Type: application/json
- **Body**:
```json
{"username":"test","password":"123456"}
```

## 接口2：获取用户信息

- **Method**: GET
- **URL**: https://api.example.com/user/profile
- **Headers**:
  - Authorization: Bearer ${token}
```

## 执行生成的脚本

```bash
# 命令行执行
jmeter -n -t output/your_script.jmx -l results.jtl

# GUI 模式打开
jmeter -t output/your_script.jmx
```

## 工作流程

1. **收集接口信息** — 从 input/ 文件夹的接口文档中自动解析，或手动录入 API 的 Method、URL、Headers、Body
2. **解析测试场景** — 用自然语言描述并发数、持续时间、断言条件、变量提取等
3. **生成 JMeter 脚本** — 展示预览摘要，确认后生成 `.jmx` 文件到 output/

## 支持的断言类型

| type            | 说明                 |
| --------------- | -------------------- |
| `status_code`   | 检查 HTTP 状态码     |
| `response_time` | 检查响应时间（毫秒） |
| `json_path`     | JSON 路径值断言      |
| `response_body` | 响应体包含/等于/匹配 |

## 支持的变量提取

| source            | 说明                        |
| ----------------- | --------------------------- |
| `extractor`       | JSON Path 提取器（`$.xxx`） |
| `regex_extractor` | 正则表达式提取器            |
| `user_defined`    | 用户自定义变量              |

## 场景描述指南

见 `references/scenario_guide.md`，支持以下测试模板：

- 简单压测
- 带预热和断言
- 带参数提取
- 数据驱动（CSV 参数化）
- 多接口场景
