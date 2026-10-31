# 03 实际评估

**离线 Mock 只验证工程流程，不证明真实模型决策效果。** 本轮 live：0 PASS、0 FAIL、9 BLOCKED、1 NOT_RUN。没有模型请求，真实模型验收仍受配置阻塞。

另有网页历史 Live 完成记录 1 条，未并入本批 CLI 通过率；详见下方路径核验。

## 运行前预期与实测命令

预期在 data/evaluation_cases.json 先定义后执行；评估器不向 live 模型传入用例编号。所有时间来自实际子进程/执行器，采用 UTC；北京时间为 UTC+8。

最终采集记录：[commands.json](../examples/audit/review_after_d4402c69a4a3/commands.json)。

| 命令 | 退出码 | 实际耗时（秒） | stdout |
|---|---:|---:|---|
| `'F:\文档\ChatGPT\小影笔试\.venv\Scripts\python.exe' -m pip check` | 0 | 0.487331 | [记录](../examples/audit/review_after_d4402c69a4a3/pip-check.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\.venv\Scripts\python.exe' -m pytest -q -m 'not live' --tb=short` | 0 | 10.807003 | [记录](../examples/audit/review_after_d4402c69a4a3/offline-tests.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\.venv\Scripts\python.exe' -m kb_agent evaluate --mode mock` | 0 | 0.707204 | [记录](../examples/audit/review_after_d4402c69a4a3/mock-evaluation.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\.venv\Scripts\python.exe' -m kb_agent retrieval-eval` | 0 | 0.360475 | [记录](../examples/audit/review_after_d4402c69a4a3/retrieval-evaluation.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\.venv\Scripts\python.exe' scripts/offline_requirements_audit.py` | 1 | 0.657599 | [记录](../examples/audit/review_after_d4402c69a4a3/independent-negative-audit.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\.venv\Scripts\python.exe' -m kb_agent evaluate --mode live --provider deepseek` | 2 | 0.375443 | [记录](../examples/audit/review_after_d4402c69a4a3/live-evaluation.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\work\review_after_d4402c69a4a3\.venv\Scripts\python.exe' -m pip install -e '.[test]'` | 0 | 23.493906 | [记录](../examples/audit/review_after_d4402c69a4a3/clean-install.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\work\review_after_d4402c69a4a3\.venv\Scripts\python.exe' -m pip check` | 0 | 0.504256 | [记录](../examples/audit/review_after_d4402c69a4a3/clean-pip-check.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\work\review_after_d4402c69a4a3\.venv\Scripts\python.exe' -m kb_agent run --mode mock --input examples/inputs/normal.json --output-dir work/acceptance-normal` | 0 | 1.797704 | [记录](../examples/audit/review_after_d4402c69a4a3/clean-offline-run.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\work\review_after_d4402c69a4a3\.venv\Scripts\python.exe' -m pytest -q -m 'not live' --tb=short` | 0 | 11.169615 | [记录](../examples/audit/review_after_d4402c69a4a3/clean-offline-tests.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\work\review_after_d4402c69a4a3\.venv\Scripts\python.exe' -m pip wheel --no-deps . -w 'F:\文档\ChatGPT\小影笔试\work\review_after_d4402c69a4a3\wheels'` | 0 | 4.026261 | [记录](../examples/audit/review_after_d4402c69a4a3/clean-build-wheel.stdout.txt) |
| `'F:\文档\ChatGPT\小影笔试\work\review_after_d4402c69a4a3\.venv\Scripts\python.exe' -c 'from importlib.resources import files; import json; print(json.dumps({n: files('"'"'kb_agent'"'"').joinpath('"'"'web_static'"'"', n).is_file() for n in ['"'"'index.html'"'"','"'"'style.css'"'"','"'"'app.js'"'"']}))'` | 0 | 0.115098 | [记录](../examples/audit/review_after_d4402c69a4a3/clean-package-assets.stdout.txt) |

离线 pytest 实际结果：**107 passed, 1 deselected in 10.20s**，进程退出 0；deselected 是显式 opt-in 的 live 测试，没有算成通过。Mock 批量：10 PASS、0 FAIL、0 BLOCKED、0 NOT_RUN。本轮 live：0 PASS、0 FAIL、9 BLOCKED、1 NOT_RUN。原始记录中的退出码保持不变。

初次测试失败记录：[共享临时目录权限失败](../examples/verification/initial-temp-permission-failure.txt)；[修复时遗漏父目录](../examples/verification/second-temp-parent-failure.txt)。两次均为 33 passed、1 deselected、23 errors；未删除失败记录。

## 逐项验收

下表 PASS 仅指脚本 Mock 的工程断言，不能读作真实模型行为通过。每份 Trace 目录均有 input/output/meta。

| 用例 / 预期 | Mock 实际状态 / 判定 | Mock 证据 | 本轮 live判定 / 证据 |
|---|---|---|---|
| E01 明确答案：answered，30 天 | answered / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E01/20261031T103429_d0d66b9e03c4/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E01/20261031T103429_d0d66b9e03c4/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E01/20261031T103431_178fece7f566/trace.jsonl) |
| E02 文档冲突：needs_clarification，30/15 天 | needs_clarification / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E02/20261031T103429_150817b8edbb/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E02/20261031T103429_150817b8edbb/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E02/20261031T103431_d82b40cce8d0/trace.jsonl) |
| E03 资料外问题：insufficient_evidence | insufficient_evidence / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E03/20261031T103429_e853e13947e9/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E03/20261031T103429_e853e13947e9/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E03/20261031T103431_74d82916ec50/trace.jsonl) |
| E04 相似改写：answered，30 天 | answered / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E04/20261031T103429_3a037dcb8613/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E04/20261031T103429_3a037dcb8613/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E04/20261031T103431_9a71f569beb2/trace.jsonl) |
| E05 上下文追问：answered/needs_clarification，30 天 | answered / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E05/20261031T103429_3aba1de05d78/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E05/20261031T103429_3aba1de05d78/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E05/20261031T103431_5b089b36a24b/trace.jsonl) |
| E06 临时工具失败：answered，30 天 | answered / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E06/20261031T103429_3e9673cc084b/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E06/20261031T103429_3e9673cc084b/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E06/20261031T103431_77d89035a675/trace.jsonl) |
| E07 持续工具失败：tool_failed/step_limit | tool_failed / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E07/20261031T103429_9a4d1e29d358/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E07/20261031T103429_9a4d1e29d358/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E07/20261031T103431_e9d343f7c204/trace.jsonl) |
| E08 工具上限：step_limit | step_limit / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E08/20261031T103429_1cb32532ee85/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E08/20261031T103429_1cb32532ee85/output.json) | NOT_RUN / Mock 专用预算用例，无 live 运行 |
| E09 内容替换45天：answered，45 天 | answered / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E09/20261031T103429_acdd8ae84902/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E09/20261031T103429_acdd8ae84902/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E09/20261031T103431_052aec246d08/trace.jsonl) |
| E10 新增冲突：needs_clarification，30/15 天 | needs_clarification / PASS | [Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E10/20261031T103429_08bbdf553166/trace.jsonl) / [输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E10/20261031T103429_08bbdf553166/output.json) | BLOCKED / [live Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E10/20261031T103431_05536b93a90e/trace.jsonl) |

## 实际路径与反馈证据

没有模型请求，真实模型验收仍受配置阻塞。

成功 live 路径以本次报告 PASS、对应 action/tool_result 和最终输出共同核对，不能把配置失败 Trace 当作 ReAct 能力证明。至少需取得普通回答与冲突查证两类真实路径。

- 已有网页 Live `20261031T102314_4d5a38b88d4b`：search_documents → search_documents → read_excerpt → search_documents → answered；3 轮请求、4 次工具调用；[Trace](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/trace.jsonl) / [回答](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/output.json)。有实际延迟和用量记录，未冒充本轮新调用；缺少第二种真实冲突路径。

以下仅为执行器实际记录的 **Mock** 路径：

- E01 `20261031T103429_d0d66b9e03c4`：search_documents → read_excerpt → answered；[Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E01/20261031T103429_d0d66b9e03c4/trace.jsonl)。
- E02 `20261031T103429_150817b8edbb`：search_documents → read_excerpt → read_excerpt → search_documents → needs_clarification；[Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E02/20261031T103429_150817b8edbb/trace.jsonl)。
- E03 `20261031T103429_e853e13947e9`：search_documents → search_documents → insufficient_evidence；[Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E03/20261031T103429_e853e13947e9/trace.jsonl)。
- E06 `20261031T103429_3e9673cc084b`：search_documents → search_documents → read_excerpt → answered；[Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E06/20261031T103429_3e9673cc084b/trace.jsonl)。
- E07 `20261031T103429_9a4d1e29d358`：search_documents → search_documents → tool_failed；[Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E07/20261031T103429_9a4d1e29d358/trace.jsonl)。

E06 首个 tool_result 为 ok=false；后一个 model_request 的 tool 消息包含相同 call_id 与错误，再出现较大 step 的 action。测试 test_exact_tool_observation_in_next_request_and_history 还用独立客户端快照逐字段断言观察确实传入下一次请求。下一步实际动作没有预先写入任何事件。

E08 的请求上限 5、工具上限 2，执行两次后第三次工具动作被跳过，stop_reason=max_tool_calls。其他测试覆盖批量逐个计数、失败调用、无效最终输出修复、超时、准确原文保留及未知工具。E09 的语料哈希与 E01 不同，实际回答/引文为 45 天。E10 重新加载含 D02 的 fixture，读取双文档并进一步检索明示适用关系。

## 语义核对的边界

生产校验负责来源存在、版本、成功读取、连续原文、ID 对应和状态结构，并有限核对阿拉伯数字及常见数值/单位组合。评估另外检查数字及 claim 对应引用、费用发生后的条件、报销材料对象、冲突双方来源、读取及后续查证。尚不是完整的语义蕴含判断。

test_exact_quote_is_not_full_semantic_verification 刻意保持原文30天，却在claim中新增仅限上海办公室正式员工的限制：来源与有限数字校验仍通过。这是公开的语义局限，不应把字符串或数值匹配宣传为完全事实一致性。候选人需逐条人工检查数字、条件、对象、否定和冲突解释；本轮独立负例审查与修复前后记录见 [离线审查](06-offline-audit.md)。

## 小型检索对照

固定冲突语料和 10 条手工设定标签（由 AI 代拟，待候选人复核），7 条开发、3 条未用于调整的保留改写。查询文件和语料哈希见 [逐条召回和汇总](../examples/retrieval/comparison_7a8612fb22a4/report.json)。对照前为同一中文 bigram BM25；对照后仅加通用短语归一化，使用相同 k=3，无完整问题路由。

Recall@3 = 前三候选内相关文档数 / 标签相关文档数，按查询平均；完整召回率要求标签全部出现。冲突问题单独要求 D01、D02 都召回，命中一份不能算完整。指标不是答案准确率。

| 集合 | 查询数 | 平均 Recall@3 前→后 | 完整召回率 前→后 | 冲突双方召回 前→后 |
|---|---:|---:|---:|---:|
| all | 10 | 0.8000 → 1.0000 | 0.8000 → 1.0000 | 0.6667 → 1.0000 |
| dev | 7 | 0.8571 → 1.0000 | 0.8571 → 1.0000 | 0.5000 → 1.0000 |
| heldout | 3 | 0.6667 → 1.0000 | 0.6667 → 1.0000 | 1.0000 → 1.0000 |

Q02 的报账/凭据/上交与 Q09 的口令在归一化后召回对应材料。未根据首轮结果再调整参数或标签。样本小、标签与词表同由 AI 编写，heldout 不是第三方盲测；只能说明本次小集合结果。

## 尚未完成

- 本轮 live自动评估：0 PASS、0 FAIL、9 BLOCKED、1 NOT_RUN；本轮是否执行以命令记录为准，E08 为 Mock 专用。
- 人工语义复核、候选人个人贡献/投入：待本人确认；题号3已据截图确认。
- bash、Python 3.11、真实抗提示注入效果：NOT_RUN。
- GitHub 远程地址未配置；本次成果未提交，无最终 commit SHA。

所有报告保留运行标识及历史失败；没有以只展示成功重跑替换失败材料。
