"""Generate review indexes from actual saved artifacts; never synthesize Trace events."""
import json
import re
from pathlib import Path
import shlex
import subprocess
import sys
import argparse
import os


root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--verification-dir", type=Path, help="实际包含 commands.json 和测试 stdout 的采集目录")
args = parser.parse_args()


def latest(pattern):
    return max(root.glob(pattern), key=lambda p: p.stat().st_mtime)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def link(path, label, prefix="../"):
    relative = path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
    return f"[{label}]({prefix}{relative})"


mock_path = latest("examples/mock/evaluation_*/report.json")
live_path = latest("examples/live/evaluation_*/report.json")
retrieval_path = latest("examples/retrieval/comparison_*/report.json")
verification = ((root / args.verification_dir / "commands.json").resolve() if args.verification_dir else
                latest("examples/verification/session_*/commands.json"))
mock, live, retrieval, commands = map(load, (mock_path, live_path, retrieval_path, verification))
expected = {c["id"]: c for c in load(root / "data/evaluation_cases.json")["cases"]}
live_cases = {c["id"]: c for c in live["cases"]}
test_record = next(c for c in commands if c["name"] == "offline-tests")
test_text = (verification.parent / "offline-tests.stdout.txt").read_text(encoding="utf-8")
test_summary = next((line.strip() for line in reversed(test_text.splitlines()) if re.search(r"\d+ (?:passed|failed|error|skipped)", line)), "请查看原始 pytest 记录")
mock_counts, live_counts = mock["counts"], live["counts"]
mock_summary = "、".join(f"{v} {k}" for k, v in mock_counts.items())
live_metas = [load(root / c["directory"] / "meta.json") for c in live["cases"] if "directory" in c]
live_requests = sum(meta["steps"] for meta in live_metas)
live_summary = "、".join(f"{v} {k}" for k, v in live_counts.items())
has_live_command = any(c["name"] == "live-evaluation" for c in commands)
live_label = "本轮 live" if has_live_command else "历史 live（本轮未运行）"
progress = ("没有模型请求，真实模型验收仍受配置阻塞。" if live_requests == 0 else
            f"本批 live 实际发出 {live_requests} 次模型请求；自动检查结果不替代人工语义复核。")
if not has_live_command:
    progress = "本轮按用户要求仅做离线测试，live 为 NOT_RUN；以下 live 数据是之前的历史记录。"

web_live = []
for meta_path in root.glob("examples/live/web/*/*/meta.json"):
    meta = load(meta_path)
    if meta.get("steps", 0) and meta.get("model_requests"):
        web_live.append((meta_path.parent, meta))
web_completed = [(path, meta) for path, meta in web_live if meta.get("status") in {"answered", "needs_clarification", "insufficient_evidence"}]
web_note = f"另有网页历史 Live 完成记录 {len(web_completed)} 条，未并入本批 CLI 通过率；详见下方路径核验。"

lines = ["# 03 实际评估", "", f"**离线 Mock 只验证工程流程，不证明真实模型决策效果。** {live_label}：{live_summary}。{progress}", "", web_note, "",
         "## 运行前预期与实测命令", "", "预期在 data/evaluation_cases.json 先定义后执行；评估器不向 live 模型传入用例编号。所有时间来自实际子进程/执行器，采用 UTC；北京时间为 UTC+8。", "",
         f"最终采集记录：{link(verification, 'commands.json')}。", "", "| 命令 | 退出码 | 实际耗时（秒） | stdout |", "|---|---:|---:|---|"]
for command in commands:
    stdout = verification.parent / (command["name"] + ".stdout.txt")
    lines.append(f"| `{shlex.join(command['command'])}` | {command['exit_code']} | {command['duration_seconds']:.6f} | {link(stdout, '记录')} |")
lines += ["", f"离线 pytest 实际结果：**{test_summary}**，进程退出 {test_record['exit_code']}；deselected 是显式 opt-in 的 live 测试，没有算成通过。Mock 批量：{mock_summary}。{live_label}：{live_summary}。原始记录中的退出码保持不变。", "",
          "初次测试失败记录：" + link(root / "examples/verification/initial-temp-permission-failure.txt", "共享临时目录权限失败") + "；" + link(root / "examples/verification/second-temp-parent-failure.txt", "修复时遗漏父目录") + "。两次均为 33 passed、1 deselected、23 errors；未删除失败记录。", "",
          "## 逐项验收", "", "下表 PASS 仅指脚本 Mock 的工程断言，不能读作真实模型行为通过。每份 Trace 目录均有 input/output/meta。", "",
          f"| 用例 / 预期 | Mock 实际状态 / 判定 | Mock 证据 | {live_label}判定 / 证据 |", "|---|---|---|---|"]
index = ["# 运行材料索引", "", "全部为合成数据。离线 Mock 只验证工程流程，不证明真实模型决策效果。", "",
         f"Mock 总报告：{link(mock_path, 'report.json')}；live 总报告：{link(live_path, 'report.json')}。", "",
         "| 用例 | Mock 运行 | live 运行 |", "|---|---|---|"]
for case in mock["cases"]:
    identifier = case["id"]
    real = live_cases[identifier]
    directory = Path(case["directory"])
    mock_trace = link(directory / "trace.jsonl", "Trace")
    mock_output = link(directory / "output.json", "输出")
    real_evidence = link(Path(real["directory"]) / "trace.jsonl", "live Trace") if "directory" in real else "Mock 专用预算用例，无 live 运行"
    e = expected[identifier]
    desc = e["name"] + "：" + "/".join(e["statuses"])
    if e.get("expected_numbers"):
        desc += "，" + "/".join(e["expected_numbers"]) + " 天"
    lines.append(f"| {identifier} {desc} | {case['status']} / {case['verdict']} | {mock_trace} / {mock_output} | {real['verdict']} / {real_evidence} |")
    index.append(f"| {identifier} {case['name']} | {link(directory / 'input.json', '输入')} / {mock_output} / {mock_trace} / {link(directory / 'meta.json', '元数据')} (`{case['run_id']}`) | {real_evidence} |")
lines += ["", "## 实际路径与反馈证据", "", progress, "", "成功 live 路径以本次报告 PASS、对应 action/tool_result 和最终输出共同核对，不能把配置失败 Trace 当作 ReAct 能力证明。至少需取得普通回答与冲突查证两类真实路径。", ""]
for path, meta in web_live:
    events = [json.loads(line) for line in (path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    sequence = [e["tool_name"] if e["event"] == "tool_call" else e["output"]["status"] for e in events if e["event"] in {"tool_call", "final"}]
    lines.append(f"- 已有网页 Live `{meta['run_id']}`：{' → '.join(sequence)}；{meta['steps']} 轮请求、{meta['tool_calls']} 次工具调用；{link(path / 'trace.jsonl', 'Trace')} / {link(path / 'output.json', '回答')}。有实际延迟和用量记录，未冒充本轮新调用；缺少第二种真实冲突路径。")
for case in live["cases"]:
    if "directory" not in case or case["id"] not in {"E01", "E02", "E03", "E06", "E07"}:
        continue
    trace_path = root / case["directory"] / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    if not any(e["event"] == "action" for e in events):
        continue
    sequence = [e["tool_name"] if e["event"] == "tool_call" else e["output"]["status"] for e in events if e["event"] in {"tool_call", "final"}]
    lines.append(f"- live {case['id']} / {case['verdict']} `{case['run_id']}`：{' → '.join(sequence)}；{link(trace_path, 'Trace')}。")
lines += ["", "以下仅为执行器实际记录的 **Mock** 路径：", ""]
for case in mock["cases"]:
    if case["id"] not in {"E01", "E02", "E03", "E06", "E07"}:
        continue
    trace_path = root / case["directory"] / "trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    sequence = [e["tool_name"] if e["event"] == "tool_call" else e["output"]["status"] for e in events if e["event"] in {"tool_call", "final"}]
    lines.append(f"- {case['id']} `{case['run_id']}`：{' → '.join(sequence)}；{link(trace_path, 'Trace')}。")
lines += ["", "E06 首个 tool_result 为 ok=false；后一个 model_request 的 tool 消息包含相同 call_id 与错误，再出现较大 step 的 action。测试 test_exact_tool_observation_in_next_request_and_history 还用独立客户端快照逐字段断言观察确实传入下一次请求。下一步实际动作没有预先写入任何事件。", "",
          "E08 的请求上限 5、工具上限 2，执行两次后第三次工具动作被跳过，stop_reason=max_tool_calls。其他测试覆盖批量逐个计数、失败调用、无效最终输出修复、超时、准确原文保留及未知工具。E09 的语料哈希与 E01 不同，实际回答/引文为 45 天。E10 重新加载含 D02 的 fixture，读取双文档并进一步检索明示适用关系。", "",
          "## 语义核对的边界", "", "生产校验负责来源存在、版本、成功读取、连续原文、ID 对应和状态结构，并有限核对阿拉伯数字及常见数值/单位组合。评估另外检查数字及 claim 对应引用、费用发生后的条件、报销材料对象、冲突双方来源、读取及后续查证。尚不是完整的语义蕴含判断。", "",
          "test_exact_quote_is_not_full_semantic_verification 刻意保持原文30天，却在claim中新增仅限上海办公室正式员工的限制：来源与有限数字校验仍通过。这是公开的语义局限，不应把字符串或数值匹配宣传为完全事实一致性。候选人需逐条人工检查数字、条件、对象、否定和冲突解释；本轮独立负例审查与修复前后记录见 [离线审查](06-offline-audit.md)。", "",
          "## 小型检索对照", "", f"固定冲突语料和 {len(retrieval['versions']['before']['rows'])} 条手工设定标签（由 AI 代拟，待候选人复核），7 条开发、3 条未用于调整的保留改写。查询文件和语料哈希见 {link(retrieval_path, '逐条召回和汇总')}。对照前为同一中文 bigram BM25；对照后仅加通用短语归一化，使用相同 k=3，无完整问题路由。", "",
          "Recall@3 = 前三候选内相关文档数 / 标签相关文档数，按查询平均；完整召回率要求标签全部出现。冲突问题单独要求 D01、D02 都召回，命中一份不能算完整。指标不是答案准确率。", "",
          "| 集合 | 查询数 | 平均 Recall@3 前→后 | 完整召回率 前→后 | 冲突双方召回 前→后 |", "|---|---:|---:|---:|---:|"]
for split in ("all", "dev", "heldout"):
    before = retrieval["versions"]["before"]["summary"][split]
    after = retrieval["versions"]["after"]["summary"][split]
    fmt = lambda value: "不适用" if value is None else f"{value:.4f}"
    lines.append(f"| {split} | {before['query_count']} | {fmt(before['mean_recall_at_k'])} → {fmt(after['mean_recall_at_k'])} | {fmt(before['complete_recall_rate'])} → {fmt(after['complete_recall_rate'])} | {fmt(before['conflict_both_rate'])} → {fmt(after['conflict_both_rate'])} |")
lines += ["", "Q02 的报账/凭据/上交与 Q09 的口令在归一化后召回对应材料。未根据首轮结果再调整参数或标签。样本小、标签与词表同由 AI 编写，heldout 不是第三方盲测；只能说明本次小集合结果。", "",
          "## 尚未完成", "", f"- {live_label}自动评估：{live_summary}；本轮是否执行以命令记录为准，E08 为 Mock 专用。", "- 人工语义复核、候选人个人贡献/投入：待本人确认；题号3已据截图确认。", "- bash、Python 3.11、真实抗提示注入效果：NOT_RUN。", "- GitHub 远程地址未配置；本次成果未提交，无最终 commit SHA。", "", "所有报告保留运行标识及历史失败；没有以只展示成功重跑替换失败材料。"]
(root / "docs/03-evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
(root / "examples/INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
readme_path = root / "README.md"
readme = readme_path.read_text(encoding="utf-8")
start_marker, end_marker = "<!-- evaluation-summary:start -->", "<!-- evaluation-summary:end -->"
if start_marker in readme and end_marker in readme:
    before, _, tail = readme.partition(start_marker)
    _, _, after = tail.partition(end_marker)
    readme_path.write_text(before + start_marker + "\n" + f"最新离线结果：**{test_summary}**；Mock：{mock_summary}；{live_label}：{live_summary}。{progress}{web_note}完整证据见 [评估文档](docs/03-evaluation.md)。\n" + end_marker + after, encoding="utf-8")
freeze = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], encoding="utf-8",
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
pins = [line for line in freeze.splitlines() if line and not line.startswith(("#", "-e"))]
(root / "requirements-lock.txt").write_text("# Actual Windows / CPython 3.14.7 environment snapshot; not a cross-version lock.\n" + "\n".join(pins) + "\n", encoding="utf-8")
print("Generated docs/03-evaluation.md, examples/INDEX.md, requirements-lock.txt")
