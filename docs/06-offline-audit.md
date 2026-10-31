# 06 对照项目要求的离线审查（题号3）

本文件保留2026-10-30离线阶段的历史结论；后续页面、107项测试、已有一条Live及干净环境验证见[2026-10-31提交前验收](07-acceptance-review.md)。下文“本轮”均指当时的离线阶段。

结论：工程链路可运行，四项确定性缺口已修复；尚需处理完整语义支持的缺口，并完成真实模型验收。不能仅凭单元测试或 Mock 通过认定全部功能完善。

审查依据为用户本轮提供的“3 / 企业知识问答 Agent / 100分”项目要求截图，以及最初粘贴的详细需求。截图中的题号3已同步 README 和需求文档；未从截图推断候选人身份或成绩。

**本轮严格离线：没有读取真实密钥文件，没有调用真实模型。离线 Mock 只验证工程流程，不证明真实模型决策效果。** 故意错误的模型消息均为审查 fixture，不是实际 DeepSeek 错误。

## 实际执行与结果

| 检查 | 结果 | 原始证据 |
|---|---|---|
| 包依赖检查 | PASS；No broken requirements found | [pip check](../examples/verification/session_bf8c1fe47397/pip-check.stdout.txt) |
| 离线 pytest | PASS；84 passed, 1 deselected in 1.42s | [pytest](../examples/verification/session_bf8c1fe47397/offline-tests.stdout.txt) |
| 标准 E01–E10 Mock | PASS；10/10 | [report.json](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/report.json) |
| 修复前独立负例 | FAIL；6 PASS / 5 FAIL | [原始审查报告](../examples/audit/requirements_e13e6f2b3fad/report.json) |
| 修复后独立负例 | FAIL；10 PASS / 1 FAIL | [最新审查报告](../examples/audit/requirements_a430c097d544/report.json) |
| 固定10查询检索对照 | Recall@3 0.80→1.00；冲突双源完整召回2/3→3/3 | [逐条召回](../examples/retrieval/comparison_abba26864588/report.json) |
| 真实模型决策/六项 live 验收 | NOT_RUN；按用户要求只做离线 | 本轮命令列表没有 live；审查报告 live_model_requests=0 |

实际命令、执行时间和退出码见 [commands.json](../examples/verification/session_bf8c1fe47397/commands.json)。另执行 `python scripts/offline_requirements_audit.py`，因为 A05 仍未满足，退出码为1；这是如实报告的审查失败，不是程序崩溃。

可复现命令（项目根目录 PowerShell）：

```powershell
.\.venv\Scripts\python.exe scripts/verify.py --offline-only
.\.venv\Scripts\python.exe scripts/offline_requirements_audit.py
```

`--offline-only` 本轮新加，不安排 live 子命令，也不读取 --env-file。原采集脚本曾把子命令失败吞为自身退出0，本轮同时修复为传播失败退出码，并增加三项回归测试。

## 对照截图的功能检查

| 项目要求 | 离线核验结论 | 实现/证据及边界 |
|---|---|---|
| 员工制度/产品问题的可靠答案 | 部分满足 | 工具与回答结构可用；A05 表明完整语义可靠性仍有缺口，真实模型未测 |
| 问题与可选历史 | 工程 PASS；理解 NOT_RUN | AgentInput 校验；历史以数据包传入每轮模型请求；独立客户端快照测试验证传递。不能据此证明指代理解 |
| 合成资料、文档ID、版本、稳定片段 | PASS | 无冲突9篇、冲突10篇；D01/D02为30/15天，关系字段均为空，无自行补造优先级 |
| 文档检索与片段读取工具 | PASS（词面工具） | search_documents/read_excerpt；准确原文、元数据、空查询、无命中、未知章节及结构化错误；产品FAQ A10通过 |
| 回答、引用、资料缺口、任务状态 | 工程 PASS；语义部分满足 | Pydantic JSON；读取来源/版本/连续引文/ID关联、空白回答、有限阿拉伯数值检查；A05仍待人工复核 |
| 根据工具结果补查、读取、追问或停止 | 循环机制 PASS；真实模型 NOT_RUN | 工具结果进入下一次请求，失败观察后有新 action；只有明确标注的脚本选择，不能当作真实 ReAct 效果 |
| 冲突说明、查证且不能任意选一条 | Mock PASS；真实判断 NOT_RUN | E02/E10读取双方并补查；数值与各方引用串位负例现被拒绝；不以日期、较短期限、分数作优先级 |
| 引用是否支持回答 | 部分满足 | 存在性与有限数值可验证；条件、对象、否定、隐含范围仍可能错误，A05为具体证据 |
| 替换内容后答案与动作响应证据变化 | Mock PASS；真实模型 NOT_RUN | E09原文改45后回答/引文改变；E10新增D02后多读一方并查证、澄清；E09工具顺序相同不构成失败 |
| 检索改进与对照评估 | 小样本 PASS | 同一中文bigram BM25增加通用短语归一化；固定查询/语料/标签哈希，有保留集；标签由AI代拟，待候选人复核，不是生产准确率 |

## 六项必须验收逐项映射

| 场景 | 当前离线实际行为 | 工程结果 | 真实模型结果 |
|---|---|---|---|
| 明确答案 E01 | 无冲突，引用D01原文，费用发生后30天内提交；[Trace](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/E01/20261030T143329_315a1c9aa3fe/trace.jsonl) | PASS | NOT_RUN |
| 文档冲突 E02 | 列30/15天与双方引用，读取后补查关系并请求确认；[Trace](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/E02/20261030T143329_57b76b7658d5/trace.jsonl) | PASS | NOT_RUN |
| 资料外 E03 | 两次检索后说明育儿假资料缺失，不给制度天数；[Trace](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/E03/20261030T143329_7ca99d64733f/trace.jsonl) | PASS | NOT_RUN |
| 相似改写 E04 | 同一脚本得到30天依据；[Trace](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/E04/20261030T143329_5ae5a7cfbd76/trace.jsonl) | PASS，仅流程；脚本未理解改写 | NOT_RUN |
| 上下文追问 E05 | 历史已传入并重新读依据；[Trace](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/E05/20261030T143329_f12193be0d45/trace.jsonl) | PASS，仅传递/读取；脚本未理解指代 | NOT_RUN |
| 工具失败 E06/E07 | 首次失败后新动作；持续失败明确tool_failed；[Trace](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/E06/20261030T143329_19c53f0746c2/trace.jsonl) / [Trace](../examples/mock/evaluation_2026-10-30T143329_002068+0000_9b1963/E07/20261030T143329_27417bea8a59/trace.jsonl) | PASS，重试由Mock新动作发出 | NOT_RUN |

## 独立负例与修复前后

下表的 PASS 表示正确拦截或通过该条工程检查，绝不把错误业务回答算作成功。A01/A02/A03 的错误 fixture 每次都继续提交错误，修复后会在预算内反馈错误并最终 step_limit；A06–A09只首次提交错误，随后修复完成。

| ID / 检查 | 修复前→后 | 处理与证据 |
|---|---|---|
| A01 正确引文/claim 之外夹带无依据的99天 | FAIL → PASS | 原本answer额外99天可绕过正确claim；现对answer/claim/各方表述增加有限数值核对，不放行错误成功答案。 [修复后Trace](../examples/audit/requirements_a430c097d544/A01/20261030T143330_9655245ead12/trace.jsonl) |
| A02 冲突双方的引用ID串位 | FAIL → PASS | 原本只确认双方来源都存在；现逐方核对数值与自身citation_ids，不允许30天引用15天原文。 [修复后Trace](../examples/audit/requirements_a430c097d544/A02/20261030T143330_04a0508037da/trace.jsonl) |
| A03 空白回答不能标记answered | FAIL → PASS | 原本空格满足字符串min_length；现返回EMPTY_ANSWER并请求修复。 [修复后Trace](../examples/audit/requirements_a430c097d544/A03/20261030T143330_57f42aac30e5/trace.jsonl) |
| A04 合法两文档语料的检索边界 | FAIL → PASS | 原本把非正BM25分数当无匹配；现按共享token筛候选，分数仅排序，1/2篇合法语料有回归测试。 [观察结果](../examples/audit/requirements_a430c097d544/report.json) |
| A05 无原文依据的范围/对象限制 | FAIL → FAIL | 仍漏检“仅限上海办公室正式员工、实习生不适用”的新增范围；原文没这些条件。保持FAIL，不用硬编码词表假装解决语义。 [修复后Trace](../examples/audit/requirements_a430c097d544/A05/20261030T143330_6a33427bde9f/trace.jsonl) |
| A06 错版本引用反馈后修复 | PASS → PASS | 错版本先被拒绝，修复后输出准确引用。 [修复后Trace](../examples/audit/requirements_a430c097d544/A06/20261030T143330_c824f6e22afa/trace.jsonl) |
| A07 改写/错误原文反馈后修复 | PASS → PASS | 引文不是原文连续片段时被拒绝，修复后通过。 [修复后Trace](../examples/audit/requirements_a430c097d544/A07/20261030T143330_158cb3c1dcbe/trace.jsonl) |
| A08 未读取的文档引用被拦截 | PASS → PASS | 本次未读过的文档不能引用，修复后重新使用已读取原文。 [修复后Trace](../examples/audit/requirements_a430c097d544/A08/20261030T143330_e924dab179c3/trace.jsonl) |
| A09 不存在的claim引用ID被拦截 | PASS → PASS | 不存在的claim citation_id被拒绝并反馈。 [修复后Trace](../examples/audit/requirements_a430c097d544/A09/20261030T143330_db1b97a4c55d/trace.jsonl) |
| A10 报销之外的产品FAQ检索/读取 | PASS → PASS | 产品客服FAQ可检索D10并准确读取工作日09:00至18:00；只验证工具。 [观察结果](../examples/audit/requirements_a430c097d544/report.json) |
| A11 生产决策模块不按固定文档/用例ID路由 | PASS → PASS | 关键生产模块未发现D01/D02或E01/E02/E09/E10固定ID字面量；Mock/评估中的ID属于允许的fixture。 [观察结果](../examples/audit/requirements_a430c097d544/report.json) |

修复前的负例输出与 Trace 完整保留，不用后来的成功结果覆盖。审查器单独列出这些“故意错误的fixture”，仍核对其文件、事件、工具反馈、计数一致性，不把它们计为业务通过。最新审查报告附关键实现SHA256以便复核。

## 仍需完善的部分

1. **P1：完整语义支持/人工审阅记录。** A05用同样30天却新增范围，仍能形成结构有效的answered。数值检查不理解条件、对象、否定、单位换算或中文数字。不能声称事实一致性已完全解决。后续应对真实样本逐claim/冲突方人工核对，并保留审阅结果；需要自动语义审查时，应独立评估误报漏报。

2. **P0验收证据：真实动态决策尚未运行。** 所有Mock分支属于测试，不证明真实模型会改写、理解追问、发现/查证冲突或从错误恢复。本轮尊重离线要求，没有用密钥完成这些验收；至少普通与冲突两种真实路径仍待后续取得。

3. **检索精度限制。** 完整问题“公司育儿假有多少天”可因“公司”词面匹配召回发票文档D06，它并无育儿假依据。工具返回的是候选，模型必须排除偏题内容。后续live需包含这类共用词的资料外问题，不能把候选分数当相关性或答案准确率。

4. **交付待确认。** 候选人亲自运行、修改、理解和投入尚待本人填写；无远程URL、未提交，无本次最终SHA。Python3.11、bash与真实抗提示注入效果未测试。

本轮没有新增界面、部署、多Agent或向量数据库。题目允许CLI，当前应优先完成上述证据与语义复核，再增加非必需功能。
