from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class AgentInput(StrictModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class Section(StrictModel):
    section_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Document(StrictModel):
    doc_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    version_date: str
    synthetic: Literal[True]
    scope: str | None = None
    supersedes: str | None = None
    priority: str | None = None
    sections: list[Section] = Field(min_length=1)

    @field_validator("version_date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def unique_sections(self):
        ids = [s.section_id for s in self.sections]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate section_id")
        return self


class Corpus(StrictModel):
    synthetic: Literal[True]
    description: str
    documents: list[Document] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_documents(self):
        ids = [d.doc_id for d in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate doc_id")
        return self


class Citation(StrictModel):
    citation_id: str = Field(min_length=1)
    doc_id: str
    version_date: str
    section_id: str
    quote: str = Field(min_length=1)


class Claim(StrictModel):
    text: str = Field(min_length=1)
    citation_ids: list[str] = Field(min_length=1)


class ConflictSide(StrictModel):
    statement: str = Field(min_length=1)
    citation_ids: list[str] = Field(min_length=1)


class Conflict(StrictModel):
    issue: str
    sides: list[ConflictSide] = Field(min_length=2)


Status = Literal[
    "answered", "needs_clarification", "insufficient_evidence", "tool_failed",
    "step_limit", "model_error",
]


class FinalAnswer(StrictModel):
    status: Status
    answer: str = Field(min_length=1)
    claims: list[Claim]
    citations: list[Citation]
    conflicts: list[Conflict]
    knowledge_gaps: list[str]
    clarification_question: str | None
    stop_reason: str = Field(min_length=1)
    run_id: str


class SearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(ge=1, le=10)
    purpose: str = Field(min_length=1, max_length=300)


class ReadArgs(StrictModel):
    doc_id: str = Field(min_length=1, max_length=100)
    section_id: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=300)


def tool_definitions() -> list[dict]:
    definitions = []
    for name, schema, description in [
        ("search_documents", SearchArgs, "检索候选原文线索。分数只用于排序，不代表制度优先级。搜索摘要不能作为最终引用。"),
        ("read_excerpt", ReadArgs, "读取指定文档的准确短章节，得到可引用原文及元数据。"),
    ]:
        definitions.append({"type": "function", "function": {
            "name": name, "description": description,
            "parameters": schema.model_json_schema(), "strict": True,
        }})
    return definitions
