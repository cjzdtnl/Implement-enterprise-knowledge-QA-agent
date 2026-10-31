# 企业知识问答 Agent

面向查找公司制度、产品 FAQ 的员工，提供问题与可选历史，返回中文回答、原文引用、冲突、资料缺口与任务状态。**全部材料为合成数据。题号 3（依据用户提供的项目要求截图）。**

当前工作目录为 `F:\文档\ChatGPT\小影笔试`，2026-10-30 从上一轮交付恢复工程并增加 DeepSeek 适配。原有运行记录完整保留。

<!-- evaluation-summary:start -->
最新离线结果：**107 passed, 1 deselected in 10.20s**；Mock：10 PASS、0 FAIL、0 BLOCKED、0 NOT_RUN；本轮 live：0 PASS、0 FAIL、9 BLOCKED、1 NOT_RUN。没有模型请求，真实模型验收仍受配置阻塞。另有网页历史 Live 完成记录 1 条，未并入本批 CLI 通过率；详见下方路径核验。完整证据见 [评估文档](docs/03-evaluation.md)。
<!-- evaluation-summary:end -->

**离线 Mock 只验证工程流程，不证明真实模型决策效果。** Mock 是显式脚本 fixture，只覆盖演示场景，不是通用问答模型；改写理解、冲突判断、错误后的决策能力仍需 live 验证。

## 评审入口

| 材料 | 内容 |
|---|---|
| [需求](docs/01-requirements.md) | 范围与六项验收 |
| [方案](docs/02-solution.md) | 模型/程序边界、工具、引用、预算 |
| [评估](docs/03-evaluation.md) | E01–E10 逐项结果和可点击 Trace |
| [离线审查](docs/06-offline-audit.md) | 对照题号3截图、独立负例、四项修复和剩余语义缺口 |
| [提交前验收](docs/07-acceptance-review.md) | 2026-10-31代码/证据审查、修复前后、干净环境和11项结论 |
| [讲解与自查](docs/08-project-walkthrough.md) | 讲解稿、真实Trace解读、八个追问、15—20分钟亲手练习 |
| [AI 使用](docs/04-ai-usage.md) | 生成范围、实际参考、候选人待确认项 |
| [复盘](docs/05-retrospective.md) | 实际失败、修复及剩余工作 |
| [运行索引](examples/INDEX.md) | 正常、缺口、故障等实际产物 |

检索 10 条固定小样本平均 Recall@3：0.80 → 1.00，不是回答准确率。最新测试、Mock/live 判定和 Trace 入口见上方评估文档。

## 环境与安装

Python 3.11+；实际安装和验证平台为 Windows / Python 3.14.7。未实际验证 Python 3.11 或 bash 环境。`src` 包可安装，测试包含在仓库外目录启动 CLI 的检查，无须设置 PYTHONPATH。

Windows PowerShell（在本仓库根目录）：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m kb_agent run --mode mock --input examples/inputs/normal.json --output-dir examples/mock/normal
.\.venv\Scripts\python.exe -m pytest -q -m "not live"
.\.venv\Scripts\python.exe -m kb_agent evaluate --mode mock
.\.venv\Scripts\python.exe scripts/verify.py --offline-only
```

bash（等价步骤，当前会话未执行）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python -m kb_agent run --mode mock --input examples/inputs/normal.json --output-dir examples/mock/normal
python -m pytest -q -m "not live"
python -m kb_agent evaluate --mode mock
python scripts/verify.py --offline-only
```

下文 `python` 指已安装本包的解释器；PowerShell 可替换成 `.\.venv\Scripts\python.exe`。直接依赖在 `pyproject.toml` 固定；`requirements-lock.txt` 是本次 Windows/Python 3.14 的依赖快照。其中 NumPy 2.5.4 要求 Python >=3.12，在 Python 3.11 上使用 pyproject 安装，让 pip 解析兼容的传递依赖；不能宣称该快照在 3.11 验证过。

## 本机可视化验收

在仓库根目录完成安装后运行：

```powershell
.\.venv\Scripts\python.exe -m kb_agent serve --port 8765
```

打开 <http://127.0.0.1:8765>。选择 E01–E10 和 Mock 可离线检查工程流程；切换真实模型、输入 DeepSeek API Key 和可用模型名后运行 Agent。页面支持问题、历史、语料副本编辑、故障注入、预算、引用原文、逐步 Trace、运行记录、产物下载和单独的人工复核记录。

API Key 只在当前页面及本机请求/任务内存中使用，不写浏览器存储、运行产物或 Git；刷新页面后需重新输入。网页不读取 `.env`。关闭服务终端可停止；CLI 仍支持显式配置文件。服务只监听本机，不含登录或公网部署能力。页面自动断言和候选人语义复核分别记录，不能把 Mock 或自动 PASS 当作真实模型六项验收通过。

## 真实模型

使用服务商支持 **Chat Completions 原生 function tools** 的实际模型。通用profile模型名没有默认值，DeepSeek的文档默认值见下节，不推测账号权限。BASE_URL 填 API 根路径（常见包含 `/v1`），程序追加 `/chat/completions`。本实现不支持只接受 Responses API 的模型；接口选择依据 [OpenAI 官方工具调用文档](https://developers.openai.com/api/docs/guides/function-calling)。其他兼容服务商仍须按其官方文档核对兼容性，当前未验证。

`.env.example` 仅是模板，程序不自动读取 `.env`，现在可用 `--env-file .env` 显式读取。进程环境变量优先于文件；`--provider` 优先于文件中的服务商选择。文件仅支持白名单变量、可选外层引号、整行注释，不执行命令或变量展开。在本地终端安全设置环境变量，密钥不写入示例或 Git：

```powershell
$env:LLM_API_KEY = Read-Host '输入 API key（仅当前终端进程）' -MaskInput
$env:LLM_BASE_URL = Read-Host '输入服务商 API 根路径'
$env:LLM_MODEL = Read-Host '输入可用且支持原生 tools 的模型名'
.\.venv\Scripts\python.exe -m kb_agent run --mode live --input examples/inputs/normal.json --output-dir examples/live/normal
.\.venv\Scripts\python.exe -m kb_agent evaluate --mode live
```

`-MaskInput` 适用于 PowerShell 7；Windows PowerShell 5.1 可用下列输入替换第一行：

```powershell
$secureKey = Read-Host '输入 API key' -AsSecureString
$env:LLM_API_KEY = [System.Net.NetworkCredential]::new('', $secureKey).Password
```

```bash
read -rsp 'API key: ' LLM_API_KEY; echo
export LLM_API_KEY
read -rp 'API base URL: ' LLM_BASE_URL; export LLM_BASE_URL
read -rp 'Model: ' LLM_MODEL; export LLM_MODEL
python -m kb_agent run --mode live --input examples/inputs/normal.json --output-dir examples/live/normal
python -m kb_agent evaluate --mode live
```

live 配置、网络或服务失败均不会切换 Mock。成功/澄清/资料不足退出码为 0，服务失败或预算耗尽为 2；批量评估含 FAIL/BLOCKED/NOT_RUN 时退出 2。因此 live 中 E08 的 Mock 专用预算用例保留 NOT_RUN，即便其他项目通过，批量命令仍退出 2，应查看 report.json。

## DeepSeek（2026-10-30 已核对官方文档）

使用标准地址 `https://api.deepseek.com`，profile 默认模型为官方文档列出的 `deepseek-flash`，可通过 `LLM_MODEL` 改为账号实际可用模型。profile 显式设置 `thinking.type=disabled`，不发送 Beta 的 `strict` 标记，本地 Pydantic 校验继续执行；模型仍通过原生 tool_calls 逐轮选择动作。此实现不支持需回传隐藏 reasoning_content 的思考模式。依据：[首个调用](https://api-docs.deepseek.com/en/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[请求参数](https://api-docs.deepseek.com/api/create-chat-completion/)。账号权限、余额及实际模型效果需真实调用确认。

在本机 `.env` 只填写 `LLM_API_KEY=实际密钥` 即可，或复制 `.env.deepseek.example` 并修改密钥。不要覆盖已有配置；真实 `.env` 被 Git 忽略。也支持 `DEEPSEEK_API_KEY`，`LLM_API_KEY` 优先。

PowerShell（必须在当前项目根目录执行）：

```powershell
.\.venv\Scripts\python.exe -m kb_agent run --mode live --provider deepseek --env-file .env --input examples/inputs/normal.json --output-dir examples/live/deepseek-normal --timeout-seconds 60 --run-timeout-seconds 300
.\.venv\Scripts\python.exe -m kb_agent run --mode live --provider deepseek --env-file .env --input examples/inputs/normal.json --corpus data/conflict.json --output-dir examples/live/deepseek-conflict --timeout-seconds 60 --run-timeout-seconds 300
.\.venv\Scripts\python.exe -m kb_agent evaluate --mode live --provider deepseek --env-file .env
.\.venv\Scripts\python.exe scripts/verify.py --provider deepseek --env-file .env
```

bash 使用同样参数，将解释器改为激活环境中的 `python`。没有配置密钥时仍保存明确失败，不伪造真实 Trace。环境变量或 `.env` 中的模型、超时和预算可覆盖 profile 默认项；profile 只决定传输配置，不决定业务答案。

## 切换语料、历史和故障

```bash
python -m kb_agent run --mode mock --input examples/inputs/normal.json --corpus data/conflict.json --output-dir examples/mock/conflict
python -m kb_agent run --mode mock --input examples/inputs/normal.json --corpus data/replaced_45.json --output-dir examples/mock/replaced
python -m kb_agent run --mode mock --input examples/inputs/followup.json --output-dir examples/mock/followup
python -m kb_agent run --mode mock --input examples/inputs/outside.json --mock-scenario outside --output-dir examples/mock/outside
python -m kb_agent run --mode mock --input examples/inputs/normal.json --fault first_search --output-dir examples/mock/temporary-failure
python -m kb_agent run --mode mock --input examples/inputs/normal.json --fault always_search --output-dir examples/mock/persistent-failure
python -m kb_agent run --mode mock --input examples/inputs/normal.json --mock-scenario endless --max-steps 5 --max-tool-calls 2 --output-dir examples/mock/limit
python -m kb_agent retrieval-eval
python scripts/verify.py
```

故障开关同样支持 live；live 不使用 `--mock-scenario`。Mock 默认脚本固定演示报销主题，因此其他任意问题应使用 live；不能将默认 Mock 当作模型。

`data/no_conflict.json` 有 9 份文档，`data/conflict.json` 有 10 份并加入 D02，`data/replaced_45.json` 将 D01 的 30 天替换为 45 天。编辑/替换 JSON 后用 `--corpus 路径` 重新加载，不使用持久缓存。每份文档有版本和稳定 section_id；scope/supersedes/priority 为 null 表示原文未提供，日期和分数不授予制度优先级。

配置项：`MAX_STEPS=12`、`MAX_TOOL_CALLS=10`、`LLM_TIMEOUT_SECONDS=30`、`RUN_TIMEOUT_SECONDS=180`；run 命令可用相应 `--max-steps`、`--max-tool-calls`、`--timeout-seconds`、`--run-timeout-seconds` 覆盖。总超时在调用边界检查，HTTP 超时针对连接/读写阶段，不是强制终止线程的硬实时期限。

## 输出与代码

每次有效运行在 `--output-dir/run_id/` 新建 `input.json`、`output.json`、`trace.jsonl`、`meta.json`。语料和输入预检错误在建立运行目录之前返回；不会留下半份运行记录。Trace 当场追加，记录可见动作、工具参数、完整短观察、模型下一次实际请求、校验错误和最终状态，不保存隐藏 reasoning。示例输入和原文均为合成材料；真实使用时 Trace 含问题/历史/证据，应按组织数据要求保管。

| 文件 | 职责 |
|---|---|
| `src/kb_agent/model.py` / `config.py` | ModelClient 协议、通用/DeepSeek 适配、显式安全配置读取；无传输自动重试 |
| `runner.py` | 原生单 Agent 循环、消息反馈、预算、实时 Trace 与产物 |
| `retrieval.py` / `tools.py` | 一致中文 bigram BM25、准确读取、统一错误、故障注入 |
| `schema.py` / `validation.py` | Pydantic 结构、来源和引用校验 |
| `prompt.py` | 模型行为约束、数据隔离、输出契约 |
| `mock.py` | 显式离线脚本 fixture，live 不导入 |
| `cli.py` / `evaluation.py` | CLI、预先固定用例和检索对照 |

来源校验要求引文准确存在，并对 answer、claims 和冲突各方增加有限的阿拉伯数值及常见数值/单位组合对应检查，避免把30天引用成30年；这不证明完整语义支持，也不进行数学计算、单位换算或中文数字理解。数值正确但范围、对象或否定含义错误仍可能漏检，待人工/live 复核。独立负例及修复前后结果见 [离线审查](docs/06-offline-audit.md)和[提交前验收](docs/07-acceptance-review.md)。

## GitHub 提交

本地 Git 已初始化为 main，**未提交、未配置远程 URL，无本次 commit SHA**。不要把任意旧 HEAD 当作最终成果。先填写 [AI 使用记录](docs/04-ai-usage.md) 的个人贡献和投入，补齐 live 验证，再提交。以下操作由候选人在确认材料后执行：

交付压缩包不包含 `.git` 和虚拟环境；从压缩包解压后先运行 `git init -b main`，再按安装步骤创建环境。

```bash
git status --short
git add README.md pyproject.toml requirements-lock.txt .env.example .env.deepseek.example .gitignore LICENSE NOTICE.md src tests data docs examples scripts
git diff --cached --stat
git diff --cached --check
git commit -m "Implement auditable enterprise knowledge QA agent"
git remote add origin YOUR_ACTUAL_GITHUB_REPOSITORY_URL
git push -u origin main
git remote get-url origin
git rev-parse HEAD
```

`YOUR_ACTUAL_GITHUB_REPOSITORY_URL` 是必须替换的占位符，当前没有可报告的真实仓库地址。Git 作者身份也须由候选人按本人信息配置。提交之后运行最后两条命令，取得真实 URL 和最终 SHA；继续修改后应重新提交并再次读取 SHA。
