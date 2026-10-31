from __future__ import annotations

from decimal import Decimal
import re
import unicodedata

from .schema import Citation, FinalAnswer
from .tools import ToolExecutor


def unsupported_numbers(text: str, citations: list[Citation]) -> list[str]:
    """Conservative Arabic-number consistency screen, not semantic entailment.

    Exact source identifiers/dates may appear in prose. Do not treat their digits
    as policy quantities, or let metadata dates justify arbitrary policy numbers.
    No arithmetic/unit conversion or Chinese-numeral understanding is claimed.
    """
    text = unicodedata.normalize("NFKC", text)
    for value in sorted({v for c in citations for v in (c.citation_id, c.doc_id, c.section_id, c.version_date)}, key=len, reverse=True):
        if value:
            text = text.replace(unicodedata.normalize("NFKC", value), " ")
    numbers = lambda value: {Decimal(n) for n in re.findall(r"\d+(?:\.\d+)?", value)}
    source = " ".join(unicodedata.normalize("NFKC", c.quote) for c in citations)
    return sorted(str(n.normalize()) for n in numbers(text) - numbers(source))


def numeric_support_errors(answer: FinalAnswer) -> list[dict]:
    by_id = {c.citation_id: c for c in answer.citations}
    fields = [(f"claims[{i}]", claim.text, [by_id[x] for x in claim.citation_ids if x in by_id])
              for i, claim in enumerate(answer.claims)]
    for i, conflict in enumerate(answer.conflicts):
        for j, side in enumerate(conflict.sides):
            fields.append((f"conflicts[{i}].sides[{j}]", side.statement,
                           [by_id[x] for x in side.citation_ids if x in by_id]))
    if answer.status in {"answered", "needs_clarification"} and answer.citations:
        fields.append(("answer", answer.answer, answer.citations))
    errors = []
    for field, text, sources in fields:
        missing = unsupported_numbers(text, sources)
        if missing:
            errors.append({"code": "UNSUPPORTED_NUMBER", "message": f"{field} 中的阿拉伯数值未能在对应原文核对：{', '.join(missing)}"})
        quantities = unsupported_quantities(text, sources)
        if quantities:
            errors.append({"code": "UNSUPPORTED_QUANTITY", "message": f"{field} 中的数值与单位组合未能在对应原文核对：{', '.join(quantities)}"})
    return errors


def unsupported_quantities(text: str, citations: list[Citation]) -> list[str]:
    """Finite quantity/unit consistency, without conversion or semantic claims.

    30 years and 30 days must not match just because their digits agree. Keep
    workdays and unspecified days distinct. Unknown units/Chinese numerals,
    policy subjects, negation and scope still require semantic review.
    """
    pattern = r"(?<![\d.])(\d+(?:\.\d+)?)\s*(个工作日|个自然日|工作日|自然日|小时|分钟|个月|字符|天|年|月|日|周|秒|元|%)"

    def quantities(value):
        normalized = unicodedata.normalize("NFKC", value)
        return {(Decimal(number), unit.removeprefix("个")) for number, unit in re.findall(pattern, normalized)}

    source = " ".join(c.quote for c in citations)
    missing = quantities(text) - quantities(source)
    return sorted(f"{number:f}{unit}" for number, unit in missing)


def validate_answer(answer: FinalAnswer, tools: ToolExecutor, run_id: str) -> list[dict]:
    errors = []

    def add(code, message):
        errors.append({"code": code, "message": message})

    if not answer.answer.strip():
        add("EMPTY_ANSWER", "answer 不能只有空白")
    if answer.run_id != run_id:
        add("RUN_ID_MISMATCH", "run_id 必须为本次运行标识")
    ids = [c.citation_id for c in answer.citations]
    if len(ids) != len(set(ids)):
        add("DUPLICATE_CITATION", "citation_id 必须唯一")
    for citation in answer.citations:
        if not citation.quote.strip():
            add("EMPTY_QUOTE", f"{citation.citation_id}: 引文不能只有空白")
        key = (citation.doc_id, citation.section_id)
        loaded = tools.kb.sections.get(key)
        read = tools.read_evidence.get(key)
        if not loaded or citation.version_date != loaded["version_date"]:
            add("SOURCE_MISMATCH", f"{citation.citation_id}: 文档、章节或版本不匹配")
        if not read:
            add("SOURCE_NOT_READ", f"{citation.citation_id}: 本次运行未成功读取")
        elif citation.version_date != read["version_date"] or citation.quote not in read["text"]:
            add("QUOTE_MISMATCH", f"{citation.citation_id}: 引文必须是本次读取原文的准确连续片段")
    referenced = set()
    for claim in answer.claims:
        referenced.update(claim.citation_ids)
    for conflict in answer.conflicts:
        for side in conflict.sides:
            referenced.update(side.citation_ids)
    for missing in referenced - set(ids):
        add("UNKNOWN_CITATION", f"未知 citation_id: {missing}")
    if answer.status == "answered" and (not answer.claims or not answer.citations):
        add("ANSWER_WITHOUT_EVIDENCE", "answered 必须有关键结论及引用")
    if answer.status == "answered" and answer.conflicts:
        add("UNRESOLVED_CONFLICT", "存在未解冲突时不得标记 answered")
    if answer.conflicts and answer.status != "needs_clarification":
        add("CONFLICT_STATUS", "列出的未解冲突需要 needs_clarification")
    if answer.status == "needs_clarification" and not answer.clarification_question:
        add("MISSING_QUESTION", "需要明确的澄清问题")
    if answer.status == "insufficient_evidence" and not answer.knowledge_gaps:
        add("MISSING_GAP", "资料不足时必须列出缺口")
    errors.extend(numeric_support_errors(answer))
    return errors
