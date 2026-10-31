# 项目讲解与自查（依据2026-10-31仓库证据）

所有讲解以当前代码与实际文件为依据，不补写模型动作，不代认候选人贡献。工程107项离线测试通过；只有一条成功Live记录，其余现有Live记录均为CONFIG_MISSING。真实冲突路径仍缺失。

## 1. 200—300字讲解草稿

这个项目面向查询公司制度或产品资料的员工，输入问题和可选历史，输出带文档版本、原文引用、资料缺口和任务状态的回答。核心使用原生工具调用：模型逐轮选择检索、读取、补查或结束，程序执行动作，再把结构化工具结果回传模型，同时校验引用、记录Trace并控制预算。检索采用中文双字切分和BM25，配合少量短语归一化。工程已通过107项离线测试及干净环境验证；已有一条DeepSeek正常问答记录。冲突、资料外、追问和故障路径目前主要有Mock工程证据，真实模型验收尚未补齐；适用范围等完整语义仍需人工核对。

依据：[执行器](../src/kb_agent/runner.py)、[检索](../src/kb_agent/retrieval.py)、[测试原始输出](../examples/audit/review_after_d4402c69a4a3/offline-tests.stdout.txt)、[已有Live](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/meta.json)。

## 2. 按实际Trace讲解

### A. 成功的真实模型路径

运行标识：`20261031T102314_4d5a38b88d4b`。实际输入是“报销材料最晚什么时候提交？”，history为空，语料为no_conflict.json。

材料：[input](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/input.json)、[Trace](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/trace.jsonl)、[output](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/output.json)、[meta](../examples/live/web/live_454d2dc0c4ae4cdfae676564/20261031T102314_4d5a38b88d4b/meta.json)。下面的行号指JSONL物理行。

| 轮次/Trace行 | 模型发出的动作与实际参数 | 工具返回 | 下一步/状态 |
|---|---|---|---|
| 1，L3–7 | 同一action发两次search_documents：query=`报销材料提交时限 最晚什么时候提交`，top_k=6；query=`费用报销管理办法 报销期限 月度 跨月 跨年`，top_k=6 | 首次返回D01/D09/D03/D06，第二次D01/D09/D06；D01预览30天，D09是审批后7工作日付款，不能混作提交期限 | L8下一轮model_request包含两份对应call_id的tool结果；由模型决定接下来读取什么 |
| 2，L9–13 | 同一action发read_excerpt(doc_id=D01,section_id=S01)，purpose为核对期限与适用条件；另发search_documents(query=`报销材料 特殊情形 例外 延期 季度 年度 截止日`,top_k=8) | 读取准确原文“报销材料须在费用发生后 30 天内提交。”，版本2025-01-10，scope/supersedes/priority均null；补查返回D01/D09/D06 | 两个动作都是模型看过首轮候选后同时提出的；不能讲成“读完本轮D01后才决定补查”。执行器顺序执行两次工具 |
| 3，L14–16 | L14请求带上读取原文和补查结果；L15模型不再发工具，直接给最终JSON | 无新工具执行 | answered：费用发生后30天内提交报销材料，C1引用D01/S01；另说明工作日/自然日及例外未明 |

实际是3轮模型请求、4次工具调用，耗时5.525349秒；有逐轮token和延迟记录，request_id未知为null。可证明这一条正常问答使用了真实工具循环，不能证明所有模型场景。

自查：回答数字30、单位天、条件费用发生后、对象报销材料均由所引原文支持；没有把D09的7工作日付款混入。另见[AI语义复核](../examples/audit/review_after_d4402c69a4a3/semantic-review.json)。

### B. 实际Live配置失败路径

运行标识：`20261031T103431_d82b40cce8d0`。这是一条实际执行的失败记录，**不是模型遇到冲突后的行为，也不是模型看到工具失败后的恢复**。

材料：[输入](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E02/20261031T103431_d82b40cce8d0/input.json)、[Trace](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E02/20261031T103431_d82b40cce8d0/trace.jsonl)、[输出](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E02/20261031T103431_d82b40cce8d0/output.json)、[meta](../examples/live/evaluation_2026-10-31T103431_078541+0000_ff64c2/E02/20261031T103431_d82b40cce8d0/meta.json)。

| 事件 | 实际发生内容 |
|---|---|
| 输入/启动，L1 | 同一报销问题，history=[]，加载conflict.json，记录语料哈希与fault=none |
| 配置失败，L2 | 创建LiveClient时发现缺少LLM_API_KEY，产生CONFIG_MISSING；此时step=0 |
| 模型动作与工具参数/返回 | **均没有**。model_requests=[]，steps=0，tool_calls=0；未发送HTTP请求 |
| 终止，L3 | 执行器返回model_error，stop_reason=CONFIG_MISSING，claims/citations/conflicts均为空；没有降级Mock |

对应代码：runner.py L83初始化LiveClient，model.py构造器检查配置，runner.py L188捕获ModelError，incomplete生成明确未完成结果。不能把E02编号或冲突语料文件名当作“真实冲突已验证”。

### C. 补充：冲突工程演示，明确为Mock

[Mock Trace](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E02/20261031T103429_150817b8edbb/trace.jsonl)、[输出](../examples/mock/evaluation_2026-10-31T103429_205246+0000_6dc1c0/E02/20261031T103429_150817b8edbb/output.json)。

实际5轮：①检索“报销材料 提交 期限”，top_k=6；②读D01/S01得30天；③读D02/S01得15天；④检索“报销 适用范围 替代关系 优先级”，top_k=6，未获得明示优先关系；⑤needs_clarification，列双方原文并追问制度负责人。动作由mock.py脚本选择，只证明执行机制，不能讲成DeepSeek真实冲突决策。

## 3. 模型决策与程序控制的边界

以下行号为当前源码位置，阅读时同时看上下文。

| 职责 | 具体位置 | 讲解要点 |
|---|---|---|
| 真实模型产生业务选择 | [model.py](../src/kb_agent/model.py) L101–137；[runner.py](../src/kb_agent/runner.py) L106–143 | 请求带完整messages和工具定义，tool_choice=auto；模型返回的tool_calls决定query、top_k、doc/section与最终结束。系统提示是行为约束，不是已发生的动作 |
| 程序分派执行工具 | [tools.py](../src/kb_agent/tools.py) L29–50；runner.py L158–169 | 根据模型给出的工具名分派到允许的两个函数。这种函数路由不决定应问什么、读哪篇或答案内容 |
| 模型下一轮看到观察 | runner.py L168–169、下一轮L104–106 | 原样序列化为role=tool，关联tool_call_id；[测试](../tests/test_runner.py) L34逐字段比对实际结果与下一次请求 |
| 协议/输出校验 | runner.py L116–135、L173–186；[validation.py](../src/kb_agent/validation.py) L66起 | 拒绝非法动作、重复ID、未读/错版本/改写引文、无效JSON；将错误反馈模型修复，不替模型编造业务答案 |
| 配置与模式 | runner.py L81–87；[cli.py](../src/kb_agent/cli.py) | live/mock只替换客户端；live失败不切换Mock。评估用例ID只在evaluation中用于预期，网页case_id只匹配评估，不决定Live动作 |
| 预算/异常/Trace | runner.py L28、L97–105、L149–156、L188起 | 控制资源、逐步写可见事件、输出未完成状态；不属于模型推理能力 |

为什么具有Agent循环：检索次数、查询内容、是否读原文、是否补查与结束由模型在每轮结果后提出；执行器没有固定“检索一次→拼接→生成”的业务顺序。已有Live确实先发两次检索，下一轮读原文并补查，再结束。但只验证了一条路径，多样化真实分支仍待补齐。该结论不适用于脚本Mock。

## 4. 设计、取舍与能力边界

| 主题 | 实际方案、取舍与自查 |
|---|---|
| 两工具分工 | search_documents返回候选ID/section/标题/版本/分数/预览，适合定位；read_excerpt返回指定章节准确原文及关系元数据，成功后登记read_evidence，才可引用。搜索摘要不能替代成功读取。见tools.py与schema.py |
| 中文检索 | retrieval.py L22做NFKC、小写、少量短语归一化；中文连续文本切相邻双字，英文数字保留整词；文档/查询同函数处理，用BM25Okapi排序。无共享token不入候选；小语料零/负分也可能有匹配，分数只排序。不具备完整语义检索能力 |
| 引用校验 | validation.py核对doc/section/版本、本次成功读取、非空连续原文、citation_id及claim关联，并有限核对阿拉伯数字/常见单位。A05仍证明同样30天可附加无依据员工/地域限制；否定、对象、适用范围与完整语义须复核，不应宣称“完全防幻觉” |
| 冲突 | prompt.py要求多候选、读双方，再找明确适用范围/替代/优先关系；没有证据就列30/15与双方引用并追问。日期更新、得分高、期限短均不赋予效力；目前真实冲突效果未验证 |
| 上下文 | runner.py L91–96把原问题和历史放在untrusted_input数据包中；历史用于指代，不作为制度来源。可引用来源仍必须由工具本次读取。测试验证传递与基础隔离，不等于真实模型已正确理解所有追问或抵抗注入 |
| 停止 | 模型提交有效最终JSON则结束；默认最多12轮模型请求/10次工具调用，失败、未知工具、重试、输出修复都计数。越限step_limit；必要服务失败model_error/tool_failed。恰好用完工具预算仍可在剩余模型轮输出最终答案；再次要工具则跳过 |
| 约3小时范围 | 原生单循环、少量JSON合成资料、BM25、Pydantic/pytest，让核心链路较集中；不引入框架迁移、向量库、Embedding服务或多Agent。它适合控制初始核心范围，不代表本项目实际只用3小时。后续页面是用户追加范围，个人实际时间须本人确认 |

## 5. 八个面试追问与回答要点

| 追问 | 基于实现的回答要点/证据 |
|---|---|
| 检索漏掉相关制度怎么办？ | 先检查token与top_k候选；无共享token时提高top_k也无用。模型可改写补查，短语归一化可改善词面召回。真实例子“忘了登录暗号怎么办”当前漏D04；下方练习先固定样例再改词表。分数不能证明候选相关 |
| 文档更新如何生效，旧答案会受影响吗？ | 每次run新建KnowledgeBase，从文件读取、重新建索引并计算SHA；本轮使用内存加载快照，后续run重载。临时30→45实验已验证。产物不覆盖；但默认语料并未全部复制到每个run，只有文件名和哈希，长期更新需另保留旧语料版本，不能说已有完整版本管理 |
| D02日期更新，为什么不用15天？ | version_date标识来源版本，不自动代表替代关系；scope/supersedes/priority为null时应读双方、查证并追问。程序没有按日期/分数决定制度的分支；Mock有工程证明，真实冲突仍缺证据 |
| 模型引用错了怎么办？ | 校验SOURCE_NOT_READ/SOURCE_MISMATCH/QUOTE_MISMATCH/UNKNOWN_CITATION等；结构化反馈进入下一轮，修复占用预算。测试含先错引文再修复；数字/单位有有限检查，但A05范围扩展可能漏检，必须承认语义边界 |
| 工具失败会自动重试吗？ | ToolExecutor返回ok=false及code/message/retryable，执行器把观察回传；后续业务重试须由模型新tool_call发出。first_search/always_search可复现。HTTP客户端无自动重试；模型API失败明确终止，不切Mock。不能把注入故障描述成外部真实事故 |
| 如何防止死循环、并行调用越限？ | 每次模型请求计一步，批量tool_calls逐个顺序执行并计数，执行前查上限；失败与输出修复同样耗预算。test_runner.py测试2次已执行/第3次跳过，保留已读证据及stop_reason；总超时是调用边界检查，不是硬实时中断 |
| Mock十项通过能说明模型效果好吗？ | 不能。Mock是显式脚本fixture，只验证工程通路。当前有107离线测试、10个标准Mock PASS及一条Live E01，真实六项及第二种路径尚未完成。10查询Recall@3 0.80→1.00属于检索小样本，不是答案准确率 |
| AI做了多少，你本人做了什么？ | AI生成/修改了初版实现、测试、文档、页面及审查修复；工具和参考已写docs/04。候选人亲自阅读、复核、修改、运行和投入目前须本人确认。可以完成小修改后据实际文件/命令讲个人贡献；不能把AI操作、假设经历或自动耗时写为本人已完成 |

## 6. 15—20分钟亲手修改练习：补一个短语别名

**当前实际不足**：员工以“登录暗号”指账号密码时，两条问法均无召回，尽管D04确有重置说明。AI已保存[修改前结果](../examples/practice/login_alias_before_dbc9147aab3b/report.json)：两个正例FAIL、一个负例PASS。本轮没有修改生产词表；待你亲手完成。

这项练习只改善检索，不证明模型理解或最终问答通过；“登录暗号→账号密码”是待人工确认的业务别名。只处理这个限定短语，不把所有“暗号”映射成密码，不添加整句问题→答案路由。现有固定10查询基准不改标签。

| 分钟 | 本人操作 | 要留下的实际证据 |
|---|---|---|
| 0–3 | 在仓库根目录运行下方before命令，打开新report，确认前两条hits=[]；看D04原文 | 本人这次before目录、起始时间 |
| 3–6 | 阅读retrieval.py的tokenize，解释为何“登录暗号”和“账号密码”没有共享双字 | 自己写一句原因，不复制“已经理解”的声明 |
| 6–9 | 只在SYNONYMS增加 `"登录暗号": "账号密码",` | 实际修改文件；不要改Mock或测试期望来放行 |
| 9–13 | 新建tests/test_candidate_login_alias.py，使用下面三个断言 | 测试文件由你落地，说明测试由AI提供建议、本人执行/调整 |
| 13–17 | 运行after及两组相关测试；再跑全量离线测试（本机历史约10秒） | 新after目录、实际pytest结果；失败也保留 |
| 17–20 | 按真实发生的操作、结果和起止时间填写docs/04/05 | 尚未做的项保持待完成；不填预测成功或虚构时长 |

```powershell
# 位置：F:\文档\ChatGPT\小影笔试
.\.venv\Scripts\python.exe scripts/practice_login_alias.py --phase before
# 然后由本人修改SYNONYMS并新建测试文件，再执行：
.\.venv\Scripts\python.exe scripts/practice_login_alias.py --phase after
.\.venv\Scripts\python.exe -m pytest -q tests/test_tools.py tests/test_candidate_login_alias.py
.\.venv\Scripts\python.exe -m pytest -q -m "not live"
```

在tests/test_candidate_login_alias.py手动保存以下建议测试：

```python
from kb_agent.retrieval import KnowledgeBase
from .conftest import ROOT


def test_login_alias_retrieves_password_policy():
    kb = KnowledgeBase(ROOT / "data/conflict.json")
    assert "D04" in {h["doc_id"] for h in kb.search("忘了登录暗号怎么办", 3)}


def test_login_alias_transfers_to_another_wording():
    kb = KnowledgeBase(ROOT / "data/conflict.json")
    assert "D04" in {h["doc_id"] for h in kb.search("登录暗号忘记了去哪里重设", 3)}


def test_other_secret_phrase_does_not_gain_policy_hits():
    kb = KnowledgeBase(ROOT / "data/conflict.json")
    assert kb.search("活动接头暗号是什么", 3) == []
```

before退出1是缺口复现的预期结果；after应在真实修改有效时三项通过并退出0，尚未由你执行，不能提前写入正式结果。这三条已用于练习设计，不能再称外部盲测。没时间亲手做时保持待完成，先提交真实现状。

## 7. 本人确认清单与个人贡献记录

| 文件 | 待本人确认 | 完成后可据实写入的个人贡献 |
|---|---|---|
| docs/04-ai-usage.md | 姓名；本人实际阅读/操作/修改及时间；网页Live是否由本人发起；具体命令和run_id；可解释模块；修订AI建议；模型授权；实际远程URL/SHA | 亲自复核30天/费用发生后/报销材料与原文；亲自复现登录暗号漏召回并修改短语归一化；亲自运行测试、分析实际输出。每项附证据，没做不勾 |
| docs/05-retrospective.md | 哪次调试本人参与；实际遇到什么失败、尝试什么修改；前后结果；仍有的限制；本人主观认识与下一步 | 据实际观察解释“无共享token时增大top_k无用”；据测试说明限定别名的改善与误召回风险；据Trace区分模型选择和预算控制。不是把AI整段开发记录改成第一人称 |

截至本轮这些个人事实尚未确认。AI提供的建议和模板可引用为辅助，不能当作本人已完成的经历。另有不纳入Git的 `work/个人贡献待落实示例.md`，只提供假设完成后的表达与待填字段。
