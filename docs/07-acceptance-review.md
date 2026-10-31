# 07 小影科技校招：证据驱动验收（2026-10-31）

结论：**可运行；工程测试通过；真实模型行为仅验证了已有的一条正常回答，整体验收尚未完成。** 没有第二种真实冲突路径；A05的无依据范围/对象/否定语义仍可能漏检。不得将此仓库标为六项Live全部通过。

本次直接检查生产代码、测试、运行产物，并实际执行原有测试、独立负例、临时语料替换和全新虚拟环境安装。保留项目结构与历史失败，不提交Git、不推送远程、不代填个人贡献。

## 证据入口

- [修复前完整命令与退出码](../examples/audit/review_baseline_ae9bd3364c1a/commands.json)、[新增独立负例修复前](../examples/audit/review_baseline_ae9bd3364c1a/independent-probes.json)。
- [第一次干净环境失败](../examples/audit/review_after_c98b6bb0b9b0/clean-offline-tests.stdout.txt)：105 passed / 1 failed，网页跨来源拒绝发生WinError 10053；这次失败没有删除。
- [最终命令/耗时](../examples/audit/review_after_d4402c69a4a3/commands.json)、[汇总与实现哈希](../examples/audit/review_after_d4402c69a4a3/summary.json)。
- [本机离线测试](../examples/audit/review_after_d4402c69a4a3/offline-tests.stdout.txt)：107 passed、1 deselected。
- [干净环境离线测试](../examples/audit/review_after_d4402c69a4a3/clean-offline-tests.stdout.txt)：107 passed、1 deselected。
- [独立审查](../examples/audit/requirements_8feb02db3796/report.json)：10 PASS / 1 FAIL，A05仍FAIL。审查命令退出1，最终采集器也退出1，未掩盖失败。
- [新增负例修复后](../examples/audit/review_after_d4402c69a4a3/independent-probes.json)：B01/B02均正确拒绝。
- [已有网页Live及回传链核验](../examples/audit/review_after_d4402c69a4a3/existing-live-evidence.json)、[AI语义审阅](../examples/audit/review_after_d4402c69a4a3/semantic-review.json)。AI审阅与候选人人工确认严格区分。
- [全部六项/十个Mock用例的输入、输出、Trace、meta](../examples/INDEX.md)。
- [可观测命令窗口](acceptance-session.json)仅记实测起止，不等同候选人投入；[打包内容核验](../examples/audit/review_after_d4402c69a4a3/wheel-inspection.json)确认模块入口、三项页面资源和源码字节一致。

## 11项验收表

PASS只作用于所标注的工程检查或具体记录；PARTIAL不是全部通过。

| 要求 | 结果 | 代码位置与运行证据 | 剩余问题 |
|---|---|---|---|
| 1 模型发业务动作、观察回传、无固定路由 | 工程PASS；已有Live E01 PASS | [runner.py](../src/kb_agent/runner.py) L106调用模型、L142保存action、L166执行、L168回传；[model.py](../src/kb_agent/model.py) L105–116直接发送messages；[已有Live核验](../examples/audit/review_after_d4402c69a4a3/existing-live-evidence.json)无动作/观察不一致 | AST字面量检查仅为辅助；已逐个阅读生产模块。固定业务脚本只在显式Mock，评估ID不进入Live消息 |
| 2 两条不同真实路径、实时Trace、无冒充 | **BLOCKED（仅1条）** | [已有E01 Trace](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/trace.jsonl)：3轮、4次工具调用；[meta](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/meta.json)有实际用量/延迟，request_id未知为null；Trace.emit逐事件append/flush；transport_retries=0 | 缺真实冲突查证或其他不同结果路径。本轮[配置检查](../examples/audit/review_after_d4402c69a4a3/live-configuration.json)无密钥；9 BLOCKED/1 Mock专用NOT_RUN，不能计成9个模型失败或通过 |
| 3 本次读取、版本/章节/原文、数字条件对象 | 来源工程PASS；具体E01语义PASS；整体PARTIAL | [validation.py](../src/kb_agent/validation.py) L66起；[AI逐字段审阅](../examples/audit/review_after_d4402c69a4a3/semantic-review.json)：30天、费用发生后、报销材料逐项对照原文；[单位负例](../examples/audit/review_after_d4402c69a4a3/independent-probes.json)已拦截 | **A05 FAIL**：准确引文、相同30天仍可夹带“仅限上海正式员工”等无依据范围。AI语义审阅拒绝该负例；生产仍非完整蕴含校验 |
| 4 30/15冲突、查证、双方引用、追问 | Mock PASS；Live BLOCKED | [临时新增冲突](../examples/audit/review_after_d4402c69a4a3/mutations.json)含双方读取与补查；[prompt.py](../src/kb_agent/prompt.py)禁止按日期/分数/较短期限裁决；检索无Top-1截断编排；已有Live检索top_k为6/8 | 不能据Mock证明DeepSeek会正确发现冲突；仍需真实E02/E10 |
| 5 资料外、口语改写、历史追问 | 工程PASS；真实理解BLOCKED | [Mock映射](../examples/INDEX.md) E03/E04/E05；[test_runner.py](../tests/test_runner.py)断言历史与观察确实传入；runner以untrusted_input数据包保留历史，唯一可引用来源为本次read_evidence | Mock不是通用模型。历史注入测试只验证数据隔离，不证明真实抗注入或指代理解 |
| 6 工具错误观察、临时/持续故障、无降级 | 工程PASS；Live故障决策BLOCKED | [tools.py](../src/kb_agent/tools.py) L37工具层注入实际ok=false；[evaluation.py](../src/kb_agent/evaluation.py) L62起检查真实错误及回传；E06/E07见[索引](../examples/INDEX.md)；[B02](../examples/audit/review_after_d4402c69a4a3/independent-probes.json)防止仅凭失败状态通过 | 这些是实际工具代码执行的合成故障，不是外部生产事故。协议测试的HTTP响应为MockTransport，不能计作模型决策 |
| 7 失败、修复、重试、批量预算与终止 | 工程PASS | [runner.py](../src/kb_agent/runner.py)请求循环计步、逐调用计数、执行前上限检查；[test_runner.py](../tests/test_runner.py)断言批量2次执行/第3次跳过、无效输出修复计步、超时；E08保留step_limit与stop_reason | 恰好到工具上限仍可使用剩余模型步输出最终答案；HTTP阶段超时不是线程硬中断 |
| 8 临时副本改45、加入D02后重载 | 工程PASS；Live变化BLOCKED | [mutations.json](../examples/audit/review_after_d4402c69a4a3/mutations.json)：原始30/替换45/新增冲突三个不同哈希，记录各自fixture与run目录；未复用预置replaced_45.json，未修改data | 数值替换保持工具顺序属正常；新增冲突实际增加另一来源读取与范围检索。真实响应变化未验证 |
| 9 实际断言、独立负例、检索指标 | 工程PASS；覆盖有限 | [107项测试](../examples/audit/review_after_d4402c69a4a3/offline-tests.stdout.txt)、[独立审查](../examples/audit/requirements_8feb02db3796/report.json)；B02证明旧E07有弱断言并已修复；[检索评估](03-evaluation.md)固定10查询、k=3、查询/语料SHA、按相关文档集合算Recall | Recall@3 0.80→1.00不是回答准确率；7开发/3保留同由AI生成，非外部盲测。A05未改测试预期 |
| 10 六项材料、五份文档、AI/个人用时 | 工程映射PASS；本人材料待补 | [运行索引](../examples/INDEX.md)列六项及正常/资料不足/工具失败；五份文档已同步本机页面、107测试、已有Live及局限；[AI记录](04-ai-usage.md)、commands实际UTC时间及耗时 | 候选人姓名、贡献、亲自运行/理解、个人投入和学习体会须本人填写。自动执行窗口不能充当本人耗时 |
| 11 干净安装、入口/依赖/配置/秘密/Git | 本平台工程PASS；交付未提交 | [clean-install](../examples/audit/review_after_d4402c69a4a3/clean-install.stdout.txt)、[pip check](../examples/audit/review_after_d4402c69a4a3/clean-pip-check.stdout.txt)、[离线运行](../examples/audit/review_after_d4402c69a4a3/clean-offline-run.stdout.txt)、[测试](../examples/audit/review_after_d4402c69a4a3/clean-offline-tests.stdout.txt)、[wheel](../examples/audit/review_after_d4402c69a4a3/clean-build-wheel.stdout.txt)、[Git/敏感扫描](../examples/audit/review_after_d4402c69a4a3/git-and-secrets.json) | Windows/Python3.14.7实测，3.11/bash未测。main无commit、无remote、全部源码未跟踪；没有可报告的最终SHA。常见模式扫描不是全面泄密证明 |

## 实际修复，保留失败

1. **核心引用缺陷B01**：数字相同但单位不同仍被放行。增加常见数值/单位组合校验，逐claim、冲突方与answer检查；错误仍回传模型并受预算限制。新增5类错单位及NFKC/工作日测试，不执行单位换算或假称完整语义校验。
2. **验收弱断言B02**：原E07只看最终状态，未检索就谎报持续故障也能通过。现在要求实际SEARCH_UNAVAILABLE、后续请求含同一观察、临时故障后有恢复，持续故障不应成功。新增独立NoAttempt负例及两类回归，原业务预期不变。
3. **干净环境网页故障**：拒绝POST时未读请求体便关闭连接，在Windows出现连接中止。现在对限定大小的请求体有界限时读取，拒绝内容不解析、不执行；新增分段请求体的实际TCP回归。原失败、最终107通过均保留。
4. **材料与工具**：交付检查支持审查/网页自定义语料快照，不再因新哈希崩溃；生成器显式使用本轮命令记录、补入已有网页Live、同步测试结果与输入链接。另修复Windows下pip freeze子进程输出编码，[原失败](../examples/audit/review_after_d4402c69a4a3/doc-generation-before.json)保留。

## 复现命令

在仓库根目录PowerShell执行；安装步骤见README。每次审查新建run目录，不覆盖旧证据。

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not live"
.\.venv\Scripts\python.exe -m kb_agent evaluate --mode mock
.\.venv\Scripts\python.exe scripts/offline_requirements_audit.py
.\.venv\Scripts\python.exe scripts/review_acceptance.py --phase after --clean-env
.\.venv\Scripts\python.exe scripts/check_delivery.py
```

当前独立审查和全量验收采集器退出1是A05未通过的明确结果，不应改成0。无密钥Live退出2，模型请求数为0。若要补齐真实验收，在本机配置密钥后运行：

```powershell
.\.venv\Scripts\python.exe -m kb_agent evaluate --mode live --provider deepseek --env-file .env
```

网页也可输入Key运行，Key不持久保存，不能从历史产物恢复。至少取得冲突查证路径并覆盖六项Live场景，逐claim复核数字、单位、条件、对象、否定和适用关系。即使九个Live业务用例通过，E08为Mock专用，批量仍会因NOT_RUN退出2，应读report，不要仅看命令退出码。

## 提交前由候选人完成

- 亲自完成尚缺的真实模型路径和六项验收，保留成功/失败记录；复核本次AI对已有E01的结论。
- 复核A05等语义风险；如提交时仍未修复，明确写入限制，不宣称可靠性完全解决。
- 如实填写个人贡献、实际用时、亲自修改/运行/理解和主观学习体会。不能把本报告自动生成过程认作本人经历。
- 审阅Git暂存内容，配置本人作者身份和真实仓库地址，按README提交/推送，再读取真实URL与最终SHA。本轮未执行这些动作。
