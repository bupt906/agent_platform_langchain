"""文档审阅工具函数。

提供文档解析、句子切分、知识库检索等核心能力。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_platform.knowledge_bases.registry import KnowledgeBaseRegistry

# ── 句子切分正则 ──────────────────────────────────────────

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[。！？.!?\n])\s*"  # 中英文句末标点 + 换行后切分
)


def parse_document(file_path: str) -> str:
    """根据文件扩展名解析文档，返回全文文本。

    支持格式：txt、md、docx
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    suffix = path.suffix.lower()

    if suffix in (".txt", ".md", ".markdown"):
        return _parse_text(path)
    elif suffix == ".docx":
        return _parse_docx(path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，支持 txt / md / docx")


def _parse_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_docx(path: Path) -> str:
    try:
        from docx import Document

        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except ImportError:
        raise ImportError("python-docx 未安装，无法解析 docx 文件。请运行: pip install python-docx")


def split_sentences(text: str) -> list[str]:
    """按句子粒度切分文本，过滤空句和纯标点/空白句。

    切分策略：
    - 按 。！？.!?\n 切分
    - 保留分句长度 >= 2 个字符的句子
    - 去除纯标点/数字/空白行
    """
    raw = _SENTENCE_SPLIT_RE.split(text)
    sentences = []
    for s in raw:
        cleaned = s.strip()
        # 过滤空句、纯标点、纯数字、过短的句子
        if not cleaned:
            continue
        if len(cleaned) < 2:
            continue
        if re.match(r"^[\d\s\.\,\;\:\!\?\-—\+\(\)\[\]\{\}]+$", cleaned):
            continue
        sentences.append(cleaned)

    return sentences


async def search_knowledge_bases(
    kb_ids: list[str],
    sentence: str,
    kb_registry: KnowledgeBaseRegistry,
    top_k: int = 5,
    threshold: float = 0.3,
) -> list[dict]:
    """向量语义检索：在指定知识库中查找与句子最相关的条文。

    Args:
        kb_ids: 知识库 ID 列表
        sentence: 待审查句子
        kb_registry: 知识库注册中心
        top_k: 返回 top-k 结果
        threshold: 相似度阈值

    Returns:
        [{"kb_id": "...", "kb_name": "...", "entry": {...}, "relevance": 0.8}, ...]
    """
    results = await kb_registry.search(kb_ids, sentence, top_k=top_k, threshold=threshold)
    return [
        {
            "kb_id": r.kb_id,
            "kb_name": r.kb_name,
            "entry": r.entry,
            "relevance": round(r.relevance, 3),
        }
        for r in results
    ]


def format_kb_results_for_prompt(results: list[dict]) -> str:
    """将 KB 检索结果格式化为 LLM prompt 用的上下文文本。"""
    if not results:
        return "（无相关检索结果）"

    parts = []
    for i, r in enumerate(results, 1):
        entry = r["entry"]
        lines = [f"### 检索结果 {i}（来源：{r['kb_name']}，相关度：{r['relevance']}）"]
        for k, v in entry.items():
            if k != "原文":
                lines.append(f"- {k}：{v}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def format_review_output(results: list[dict], summary: dict) -> dict:
    """将审阅结果格式化为标准输出结构。"""
    return {
        "results": results,
        "summary": summary,
    }
