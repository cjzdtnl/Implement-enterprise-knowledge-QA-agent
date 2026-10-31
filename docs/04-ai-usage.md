# 04 AI 使用与候选人贡献

本项目由 Codex 按用户粘贴需求创建。候选人明确要求将工作位置调整为 `C:\Users\cjtnl\Desktop\求职\学习\小影笔试`，AI 随后迁入新文件；该目录最初不存在，没有覆盖已有用户项目文件。

2026-10-30 用户选择 DeepSeek API 并要求继续。AI 检查 `F:\文档\ChatGPT\小影笔试` 为空后，从上一轮交付快照复制工程（保留历史记录），在 F 盘重建环境和 Git，添加 DeepSeek profile、本机配置读取及协议/脱敏测试。用户表示会在本机配置密钥；个人是否完成、真实调用结果，以后续实际记录为准。此段不代认候选人已运行或理解代码。

## 已发生的 AI 工作

初始阶段，AI 生成/修改了 src 中的全部实现、10 份合成制度及 fixtures、Mock、测试、CLI、评估器、运行采集脚本、README 和五份说明文档；使用 PowerShell/Python 写入及检查文件，通过 pip 安装实际依赖，执行 pytest、Mock/live 配置评估、检索对照，初始化本地 Git。没有向 GitHub 推送或创建 commit，没有给他人发送消息。该阶段没有获得真实模型回答；后续已有网页 Live 的证据另列于下方。

使用工具：文件读取/补丁、PowerShell、Python 3.14.7、pip、pytest、Git、网络文档检索，以及 openai-docs 技能的接口核对流程。没有启用多 Agent。模型适配代码通过 HTTPX MockTransport 的离线协议测试，但这不是连接服务商的测试。

记录和 Trace 来自执行器/子进程实际运行，不是模型事后编写动作日志。可点击运行记录见 [评估文档](03-evaluation.md)。初次临时目录权限错误及随后漏建父目录的失败均保留。初始阶段真实 API 因配置缺失未发出 HTTP 请求，当时未报告模型名、请求 ID 或 token 实测值；后续网页记录按实际meta单独列出。

## 实际参考（访问日期：2026-10-28）

| 实际阅读 URL/文件 | 用途与采用方式 | 许可/边界 |
|---|---|---|
| [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)；[Chat Completions create](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) | 工具定义、tool_calls、tool_call_id 回传契约；自行实现 HTTP 适配与循环 | 官方 API 文档，未复制其示例实现；未采用 OpenAI SDK |
| [rank_bm25 README](https://github.com/dorianbrown/rank_bm25)、[rank_bm25.py](https://raw.githubusercontent.com/dorianbrown/rank_bm25/master/rank_bm25.py)、[LICENSE](https://raw.githubusercontent.com/dorianbrown/rank_bm25/master/LICENSE) | 阅读 BM25 初始化/评分相关少量实现及预处理要求；作为未修改依赖调用 BM25Okapi，自行实现中文处理 | Apache-2.0；库的算法和效果不归为本项目原创，未复制/修改库源码 |
| [LangGraph Agentic RAG 教程](https://docs.langchain.com/oss/python/langgraph/agentic-rag)、[仓库 LICENSE](https://raw.githubusercontent.com/langchain-ai/langgraph/main/LICENSE) | 借鉴消息状态、工具观察反馈、检索不足可改写的概念 | 仓库 MIT；未复制教程代码、未使用框架、未阅读仓库编排实现源码；不主张网页本身许可等同仓库许可 |
| [考核示例 README.md](https://raw.githubusercontent.com/lwz1357/agent-campus-submission-example/main/README.md) | 借鉴五份文档、离线入口、诚实记录 Mock 的材料组织方式 | README 已访问；main/LICENSE 请求返回 404，许可证未确认；未复制代码，不将其写成完整 ReAct 参考实现 |
| [DeepSeek 工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[接口参数](https://api-docs.deepseek.com/api/create-chat-completion/)、[首个调用](https://api-docs.deepseek.com/en/)（2026-10-30 实际访问） | 核对标准地址/模型名、默认 thinking、非思考 native tools，以及 strict 的 Beta 范围；据此调整请求 | 官方文档；未复制示例实现；服务权限/效果以实际运行记录为准 |

仅把上述已访问材料写为参考。未读取的仓库文件、未运行的开源功能不记作已研究或自主实现。[NOTICE](../NOTICE.md) 另说明第三方依赖；本项目新增代码采用 MIT。

## 候选人必须亲自填写

以下项目均为 **待候选人补充**，AI 不代写“本人独立完成”的经历：

| 项目 | 真实情况 |
|---|---|
| 姓名、题号 | 姓名待候选人补充；题号3已据用户截图确认 |
| 本人实际投入时长（含理解/修改/运行） | 待候选人补充，不能使用 AI 自动执行耗时代替 |
| 本人亲自修改的文件与理由 | 待候选人补充 |
| 本人亲自运行的命令与结果 | 待候选人补充；已记录的AI命令不计作本人执行，网页运行归属待确认 |
| 本人已理解并可解释的模块 | 待候选人补充 |
| 本人不同意或修订的 AI 建议 | 待候选人补充 |
| 真实模型服务、模型名与授权情况 | 待候选人补充，不要填写密钥 |
| 真实模型证据与人工语义复核 | 待候选人执行/确认 |
| GitHub 实际远程 URL、最终 commit SHA | 未配置远程、未提交；提交后按 README 命令读取 |
| 个人学习体会 | 待候选人补充 |

开发会话的可观测时间记录在 [development-session.json](development-session.json)，这只是 AI 工作窗口，不代表候选人个人总投入。

本轮 DeepSeek 适配另记在 [deepseek-session.json](deepseek-session.json)，不把两个日期间的空闲时间计算成开发耗时或个人投入。

用户随后明确要求先离线对照截图审查。AI 新增独立负例、离线验证开关与失败退出码传递，复现并修复四项工程缺口；剩余语义范围漏检和真实模型 NOT_RUN 如实记在 [离线审查](06-offline-audit.md)。所有错误模型输出均为刻意构造的 Mock fixture，未调用真实模型。

## 2026-10-31 页面与提交前验收

用户明确追加本机页面和输入 DeepSeek API Key 的需求。AI 增加标准库本机服务、无外部资源的HTML/CSS/JS页面、同源任务接口、密钥不落盘测试、引用/Trace/语料副本/独立人工复核功能，使用 Sites 本地开发流程与 computer-use 浏览器检查；没有发布网站。上述工作均不能写成候选人独立开发。

本轮 AI 直接读取生产循环/模型/工具/检索/校验及测试，执行原有测试和独立负例，发现并修复数值相同但单位错误仍放行、持续故障评估仅凭状态通过，以及干净环境中拒绝请求时连接提前关闭的问题。新增回归测试、临时语料对照和独立虚拟环境安装/测试/打包验证，失败与修复后目录均保留。[完整命令与证据](07-acceptance-review.md)。

仓库已有网页 Live `20261031T102314_4d5a38b88d4b`，含3轮请求、4次工具调用及用量/延迟；AI对该回答的30天、费用发生后、报销材料对象和引文做了明确复核。这是已有运行产物，未声称由本轮重新调用，也不代认候选人已完成人工复核。当前 `.env` 和进程中无可用密钥，本批新增 Live 评估为配置受阻，未产生模型HTTP请求。仍未取得第二种真实冲突路径。

本轮自动执行的起止时间和子命令耗时在验收报告的 commands.json 中，不代表候选人投入。候选人的姓名、亲自修改/运行/理解的部分、总投入和主观学习体会继续保留待本人补充。

## 讲解自查与可亲手完成的贡献项（待确认）

AI本轮新增[讲解与自查](08-project-walkthrough.md)、`scripts/practice_login_alias.py`，并在未改生产词表的情况下保存两条“登录暗号”漏召回与一条负例的实际结果。以下清单不是已完成声明：

- [ ] 本人阅读并能解释runner.py、tools.py、retrieval.py的相关代码，写下对应位置。
- [ ] 本人核对已有Live回答的30天、费用发生后、报销材料与原文，记录run_id及实际发现。
- [ ] 本人复现登录暗号检索缺口，修改限定短语别名并保存实际改动。
- [ ] 本人运行修改前后检查与相关pytest，填写真实命令、输出目录、通过/失败数量。
- [ ] 本人确认哪些建议来自AI、自己调整了什么及理由。
- [ ] 本人补充累计有效投入、模型使用授权、真实仓库URL与最终SHA。

完成的项目可据实写为“个人贡献”，每项附实际文件/命令/结果；未完成继续留空。另存的假设表达模板位于Git忽略的work目录，不作为事实记录提交。
