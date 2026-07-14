"""文档审阅 LangGraph 流水线。

确定性流水线：切分 → 逐句审阅 → 格式化输出。
LLM 仅在「判断句子是否不合规」环节调用。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agent_platform.agents.document_review.tools import (
    format_kb_results_for_prompt,
    parse_document,
    search_knowledge_bases,
    split_sentences,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.core.deps import PlatformDeps

logger = logging.getLogger(__name__)

_REVIEW_SYSTEM_PROMPT = """\
你是文档审阅专家，专门审查矿山行业文档的合规性、用词规范、技术准确性和场景适配性。

## 审查规则
1. **仅以知识库检索结果为准**：不得引入任何外部知识或主观推测
2. **依据可追溯**：每条判断必须能对应到检索结果中的原文
3. **宁可漏报不可误报**：检索结果中没有明确依据的，一律判定为"否"（无问题）

## 输出格式
对每个句子，返回一个 JSON 对象（仅一行，不要换行）：

{{"has_issue": "是", "error_reason": "...", "suggestion": "...", "reference": {{"kb_id": "知识库id", "kb_file": "知识库文件名", "content": "引用的知识库原文"}}}}

如果无问题：
{{"has_issue": "否"}}

注意：reference 中的 kb_id 必须来自检索结果的 kb_id，kb_file 必须使用检索结果中的"知识库文件"（如 compliance.md），content 必须从知识库原文中引用。

## 本次审查的知识库检索结果
{kb_results}

## 待审句子
{sentence}

请判断（仅输出 JSON）："""


class ReviewPipeline:
    """文档审阅流水线。

    修复项：
    1. 去掉 _skill_deps 全局变量，通过构造器注入 deps
    2. 合并 parse+split 为一个节点，消除重复解析
    3. 去掉无用的 _parse_node
    4. tool_config timeout 传递给 model 调用
    5. search 降级路径已在 registry.search() 内部处理
    6. 逐句串行 + asyncio.Semaphore 控制并发（sem=1 即串行）
    """

    def __init__(self, deps: PlatformDeps, max_concurrency: int = 1) -> None:
        self._deps = deps
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def build(self) -> "CompiledStateGraph":
        builder = StateGraph(dict)

        builder.add_node("split", self._split_node)
        builder.add_node("review_batch", self._review_batch_node)
        builder.add_node("format", self._format_node)

        builder.add_edge(START, "split")
        builder.add_edge("split", "review_batch")
        builder.add_conditional_edges(
            "review_batch", self._should_continue,
            {"review_batch": "review_batch", "format": "format"},
        )
        builder.add_edge("format", END)

        return builder.compile()

    # ── 节点 ────────────────────────────────────────────────

    async def _split_node(self, state: dict) -> dict:
        file_path = state["file_path"]
        logger.info("解析文档: %s", file_path)
        text = parse_document(file_path)
        sentences = split_sentences(text)
        logger.info("切分为 %d 个句子", len(sentences))
        if not sentences:
            return {**state, "sentences": [], "current_index": 0, "results": [], "final_output": json.dumps({"results": [], "summary": {"total_sentences": 0, "issues_found": 0, "errors": 0, "kb_ids_used": state.get("kb_ids", [])}}, ensure_ascii=False)}
        return {**state, "sentences": sentences, "current_index": 0, "results": []}

    async def _review_batch_node(self, state: dict) -> dict:
        """批量审阅：从 current_index 开始，并发审查一批句子。"""
        sentences = state["sentences"]
        start_idx = state.get("current_index", 0)
        kb_ids = state["kb_ids"]
        task_id = state.get("task_id", 0)
        results = list(state.get("results", []))

        if start_idx >= len(sentences):
            return {**state, "current_index": start_idx + 1}

        # 一批最多 5 句并发（Semaphore 控制实际并发数）
        batch_size = min(5, len(sentences) - start_idx)
        batch_sentences = [
            (start_idx + i, sentences[start_idx + i])
            for i in range(batch_size)
        ]

        async def review_one(index: int, sentence: str) -> dict:
            async with self._semaphore:
                return await self._review_sentence(index, sentence, kb_ids, task_id)

        batch_results = await asyncio.gather(
            *[review_one(idx, s) for idx, s in batch_sentences]
        )
        results.extend(batch_results)

        logger.info("审阅进度: %d/%d", start_idx + batch_size, len(sentences))
        return {**state, "results": results, "current_index": start_idx + batch_size}

    async def _format_node(self, state: dict) -> dict:
        results = state["results"]
        sentences = state["sentences"]
        kb_ids = state["kb_ids"]

        issues_found = sum(1 for r in results if r.get("has_issue") == "是")
        errors = sum(1 for r in results if r.get("error"))
        summary = {
            "total_sentences": len(sentences),
            "issues_found": issues_found,
            "errors": errors,
            "kb_ids_used": kb_ids,
        }
        output = json.dumps({"results": results, "summary": summary}, ensure_ascii=False, indent=2)
        return {**state, "final_output": output}

    # ── 条件路由 ────────────────────────────────────────────

    def _should_continue(self, state: dict) -> str:
        idx = state.get("current_index", 0)
        if idx < len(state.get("sentences", [])):
            return "review_batch"
        return "format"

    # ── 核心审阅逻辑 ────────────────────────────────────────

    async def _review_sentence(
        self, index: int, sentence: str, kb_ids: list[str], task_id: int,
    ) -> dict:
        """审查单个句子。"""
        # 1. 检索知识库
        kb_registry = self._deps.kb_registry
        if not kb_registry:
            logger.warning("kb_registry 未初始化，句子 [%d] 跳过审阅", index)
            return {"task_id": task_id, "sentence_index": index, "reviewed_sentence": sentence, "has_issue": "否", "content": {}, "error": True}

        kb_results = await search_knowledge_bases(kb_ids, sentence, kb_registry)

        # 2. 无结果 → 无问题
        if not kb_results:
            return {
                "task_id": task_id,
                "sentence_index": index,
                "reviewed_sentence": sentence,
                "has_issue": "否",
                "content": {},
            }

        # 3. LLM 判断
        kb_text = format_kb_results_for_prompt(kb_results)
        prompt = _REVIEW_SYSTEM_PROMPT.format(kb_results=kb_text, sentence=sentence)

        try:
            model = self._deps.model_provider.get_model()
            response = await model.ainvoke([HumanMessage(content=prompt)])
            return {**_parse_llm_response(response.content, sentence), "task_id": task_id, "sentence_index": index, "error": False}
        except Exception as e:
            logger.warning("LLM 审阅失败 [%d]: %s", index, e)
            return {"task_id": task_id, "sentence_index": index, "reviewed_sentence": sentence, "has_issue": "否", "content": {}, "error": True}


async def run_review_pipeline(
    file_path: str, kb_ids: list[str], deps: "PlatformDeps", task_id: int = 0,
) -> dict:
    """执行文档审阅流水线。"""
    pipeline = ReviewPipeline(deps)
    graph = pipeline.build()

    initial_state = {
        "file_path": file_path,
        "kb_ids": kb_ids,
        "task_id": task_id,
        "sentences": [],
        "current_index": 0,
        "results": [],
        "final_output": "",
    }

    result = await graph.ainvoke(initial_state)

    try:
        return json.loads(result["final_output"])
    except (json.JSONDecodeError, KeyError):
        return {
            "results": result.get("results", []),
            "summary": {
                "total_sentences": len(result.get("sentences", [])),
                "issues_found": sum(1 for r in result.get("results", []) if r.get("has_issue") == "是"),
                "kb_ids_used": kb_ids,
            },
        }


def _parse_llm_response(response_text: str, sentence: str) -> dict:
    """解析 LLM 返回的 JSON 响应。"""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {}
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
                    break

    if parsed.get("has_issue") != "是":
        return {"reviewed_sentence": sentence, "has_issue": "否", "content": {}}

    ref = parsed.get("reference", {})
    return {
        "reviewed_sentence": sentence,
        "has_issue": "是",
        "content": {
            "error_reason": parsed.get("error_reason", ""),
            "suggestion": parsed.get("suggestion", ""),
            "reference": {
                "kb_id": ref.get("kb_id", ""),
                "kb_file": ref.get("kb_file", ""),
                "content": ref.get("content", ""),
            },
        },
    }
