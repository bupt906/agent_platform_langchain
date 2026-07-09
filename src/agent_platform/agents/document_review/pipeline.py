"""文档审阅 LangGraph 流水线。

确定性流水线：解析 → 切分 → 逐句审阅 → 格式化输出。
LLM 仅在「判断句子是否不合规」环节调用。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

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

{{"是否有问题": "是", "错误原因": "具体描述不合规原因", "修改建议": "给出明确修改方向", "建议依据": "引用知识库原文出处"}}

如果无问题：
{{"是否有问题": "否"}}

注意：
- "是否有问题"取值为"是"或"否"
- "建议依据"必须来源于检索结果中的原文，不得编造
- 如果多个 KB 都标记了同一句子的问题，输出最严重的一个即可

## 本次审查的知识库检索结果
{kb_results}

## 待审句子
{sentence}

请判断（仅输出 JSON）："""


def _merge_results(existing: list[dict], new: list[dict]) -> list[dict]:
    merged = list(existing)
    merged.extend(new)
    return merged


class ReviewState(TypedDict):
    file_path: str
    kb_ids: list[str]
    sentences: list[str]
    current_index: int
    results: Annotated[list[dict], _merge_results]
    final_output: str
    deps: Any  # PlatformDeps


class ReviewPipeline:
    """文档审阅流水线，基于 LangGraph StateGraph 实现逐句审查。"""

    def __init__(self, deps: PlatformDeps) -> None:
        self._deps = deps

    def build(self) -> CompiledStateGraph:
        builder = StateGraph(ReviewState)

        builder.add_node("parse", self._parse_node)
        builder.add_node("split", self._split_node)
        builder.add_node("review", self._review_node)
        builder.add_node("format", self._format_node)

        builder.add_edge(START, "parse")
        builder.add_edge("parse", "split")
        builder.add_edge("split", "review")
        builder.add_conditional_edges("review", self._should_continue, {"review": "review", "format": "format"})
        builder.add_edge("format", END)

        return builder.compile()

    # ── 节点 ────────────────────────────────────────────────

    async def _parse_node(self, state: ReviewState) -> dict:
        file_path = state["file_path"]
        logger.info("开始解析文档: %s", file_path)
        text = parse_document(file_path)
        return {"sentences": [], "current_index": 0, "results": [], "final_output": "", "kb_ids": state["kb_ids"], "file_path": state["file_path"], "deps": state.get("deps")}

    async def _split_node(self, state: ReviewState) -> dict:
        file_path = state["file_path"]
        text = parse_document(file_path)
        sentences = split_sentences(text)
        logger.info("文档切分为 %d 个句子", len(sentences))
        return {"sentences": sentences}

    async def _review_node(self, state: ReviewState) -> dict:
        idx = state.get("current_index", 0)
        sentences = state["sentences"]
        kb_ids = state["kb_ids"]
        deps = state.get("deps") or self._deps

        if idx >= len(sentences):
            return {"current_index": idx + 1}

        sentence = sentences[idx]
        logger.info("审查句子 [%d/%d]: %s", idx + 1, len(sentences), sentence[:60])

        # 1. 检索知识库
        kb_registry = deps.kb_registry
        kb_results = []
        if kb_registry:
            kb_results = await search_knowledge_bases(kb_ids, sentence, kb_registry)

        # 2. 如果没有检索到相关结果 → 直接标记为无问题
        if not kb_results:
            result_entry = {"已审阅的句子": sentence, "是否有问题": "否", "content": {}}
            return {"results": [result_entry], "current_index": idx + 1}

        # 3. 调用 LLM 判断
        kb_text = format_kb_results_for_prompt(kb_results)
        prompt = _REVIEW_SYSTEM_PROMPT.format(kb_results=kb_text, sentence=sentence)

        try:
            model = deps.model_provider.get_model()
            response = await model.ainvoke([HumanMessage(content=prompt)])
            review_json = self._parse_llm_response(response.content, sentence)
        except Exception as e:
            logger.warning("LLM 审阅调用失败: %s，标记为无问题", e)
            review_json = {"已审阅的句子": sentence, "是否有问题": "否", "content": {}}

        return {"results": [review_json], "current_index": idx + 1}

    async def _format_node(self, state: ReviewState) -> dict:
        results = state["results"]
        sentences = state["sentences"]
        kb_ids = state["kb_ids"]

        issues_found = sum(1 for r in results if r.get("是否有问题") == "是")

        summary = {"total_sentences": len(sentences), "issues_found": issues_found, "kb_ids_used": kb_ids}

        output = json.dumps({"results": results, "summary": summary}, ensure_ascii=False, indent=2)
        return {"final_output": output}

    # ── 条件路由 ────────────────────────────────────────────

    def _should_continue(self, state: ReviewState) -> str:
        idx = state.get("current_index", 0)
        sentences = state["sentences"]
        if idx < len(sentences):
            return "review"
        return "format"

    # ── 工具方法 ────────────────────────────────────────────

    @staticmethod
    def _parse_llm_response(response_text: str, sentence: str) -> dict:
        """解析 LLM 返回的 JSON 响应。"""
        text = response_text.strip()

        # 去除可能的 markdown 代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 对象
            import re

            match = re.search(r"\{[^}]+\}", text)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    parsed = {"是否有问题": "否", "content": {}}
            else:
                parsed = {"是否有问题": "否", "content": {}}

        # 确保标准格式
        result = {"已审阅的句子": sentence, "是否有问题": parsed.get("是否有问题", "否"), "content": {}}

        if result["是否有问题"] == "是":
            result["content"] = {
                "错误原因": parsed.get("错误原因", ""),
                "修改建议": parsed.get("修改建议", ""),
                "建议依据": parsed.get("建议依据", ""),
            }

        return result


async def run_review_pipeline(file_path: str, kb_ids: list[str], deps: PlatformDeps) -> dict:
    """执行文档审阅流水线的便捷函数。

    Args:
        file_path: 待审阅文件路径
        kb_ids: 知识库 ID 列表
        deps: 全局依赖容器

    Returns:
        {"results": [...], "summary": {...}}
    """
    pipeline = ReviewPipeline(deps)
    graph = pipeline.build()

    initial_state: ReviewState = {
        "file_path": file_path,
        "kb_ids": kb_ids,
        "sentences": [],
        "current_index": 0,
        "results": [],
        "final_output": "",
        "deps": deps,
    }

    result = await graph.ainvoke(initial_state)

    # 解析 final_output JSON
    try:
        return json.loads(result["final_output"])
    except (json.JSONDecodeError, KeyError):
        return {
            "results": result.get("results", []),
            "summary": {
                "total_sentences": len(result.get("sentences", [])),
                "issues_found": sum(1 for r in result.get("results", []) if r.get("是否有问题") == "是"),
                "kb_ids_used": kb_ids,
            },
        }
