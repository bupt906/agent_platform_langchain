"""AI 文档审阅模块测试 — 向量 RAG 版。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_platform.agents.document_review.tools import (
    format_kb_results_for_prompt,
    parse_document,
    split_sentences,
)
from agent_platform.agents.document_review.pipeline import ReviewPipeline
from agent_platform.knowledge_bases.registry import KnowledgeBase, KnowledgeBaseRegistry, SearchResult
from agent_platform.knowledge_bases.vector_store import VectorStore


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def kb_entries():
    """预置 KB 条目数据。"""
    return [
        KnowledgeBase(
            name="测试知识库",
            description="用于测试",
            kb_id="test_kb",
            entries=[
                {"标题": "条目 1", "规则": "必须使用法定计量单位", "来源": "GB 3100", "原文": "设备参数必须使用法定计量单位，如 MPa、kW、mm"},
                {"标题": "条目 2", "规则": "禁止使用绝对化用语", "来源": "行业术语规范", "原文": "禁止使用\"绝对安全\"\"万无一失\"\"零风险\"等用语"},
            ],
        ),
        KnowledgeBase(
            name="合规知识库",
            description="合规",
            kb_id="compliance",
            entries=[
                {"标题": "条目 1", "规则": "必须取得安全生产许可证", "来源": "安全生产许可证条例"},
            ],
        ),
    ]


def make_registry_with_kbs(kb_entries: list[KnowledgeBase]) -> KnowledgeBaseRegistry:
    """创建只含 KB 元数据（无向量存储）的注册中心。"""
    reg = KnowledgeBaseRegistry()
    for kb in kb_entries:
        reg.register(kb)
    return reg


@pytest.fixture
def sample_txt_file(tmp_path):
    path = tmp_path / "test_doc.txt"
    path.write_text("这是一份安全生产方案。所有设备必须安全可靠。作业人员应持证上岗。", encoding="utf-8")
    return str(path)


@pytest.fixture
def sample_md_file(tmp_path):
    path = tmp_path / "test_doc.md"
    path.write_text("# 安全方案\n\n本次采矿绝对安全。\n\n设备参数用英制单位。", encoding="utf-8")
    return str(path)


class TestDocumentParsing:
    """文档解析测试。"""

    def test_parse_text_file(self, sample_txt_file):
        text = parse_document(sample_txt_file)
        assert "安全生产方案" in text
        assert "持证上岗" in text

    def test_parse_markdown_file(self, sample_md_file):
        text = parse_document(sample_md_file)
        assert "绝对安全" in text
        assert "英制单位" in text

    def test_parse_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            parse_document("/nonexistent/file.txt")

    def test_parse_unsupported_format(self, tmp_path):
        path = tmp_path / "test.pdf"
        path.write_text("fake pdf")
        with pytest.raises(ValueError, match="不支持"):
            parse_document(str(path))


class TestSentenceSplitting:
    """句子切分测试。"""

    def test_split_chinese_sentences(self):
        text = "这是一句话。这是第二句话！这是第三句？最后一句。"
        result = split_sentences(text)
        assert len(result) == 4

    def test_split_mixed_newlines(self):
        text = "第一段内容。\n第二段内容。\n\n第三段内容。"
        result = split_sentences(text)
        assert len(result) == 3

    def test_filter_empty_and_short(self):
        text = "有效句子。  。   .   短。"
        result = split_sentences(text)
        assert len(result) >= 1
        assert all(len(s) >= 2 for s in result)
        assert "" not in result
        assert "." not in result

    def test_preserve_sentence_content(self):
        text = "设备参数使用 MPa 单位。"
        result = split_sentences(text)
        assert "MPa" in result[0]
        assert "设备参数" in result[0]


class TestKnowledgeBaseRegistry:
    """知识库注册中心测试（元数据层面，无向量检索）。"""

    def test_register_and_get(self, kb_entries):
        reg = make_registry_with_kbs(kb_entries)
        kb = reg.get("test_kb")
        assert kb is not None
        assert kb.name == "测试知识库"
        assert len(kb.entries) == 2

    def test_get_nonexistent(self, kb_entries):
        reg = make_registry_with_kbs(kb_entries)
        assert reg.get("nonexistent") is None

    def test_list_all(self, kb_entries):
        reg = make_registry_with_kbs(kb_entries)
        all_kbs = reg.list_all()
        assert len(all_kbs) == 2

    def test_list_infos(self, kb_entries):
        reg = make_registry_with_kbs(kb_entries)
        infos = reg.list_infos()
        assert len(infos) == 2
        assert "id" in infos[0]
        assert "entry_count" in infos[0]

    def test_count(self, kb_entries):
        reg = make_registry_with_kbs(kb_entries)
        assert reg.count == 2

    def test_get_kb_contents(self, kb_entries):
        reg = make_registry_with_kbs(kb_entries)
        content = reg.get_kb_contents(["test_kb"])
        assert "测试知识库" in content

    def test_register_adds_kb(self):
        reg = KnowledgeBaseRegistry()
        kb = KnowledgeBase(name="新知识库", description="测试", kb_id="new_kb", entries=[])
        reg.register(kb)
        assert reg.count == 1
        assert reg.get("new_kb") is kb


class TestVectorStore:
    """向量存储测试（sqlite-vec）。"""

    @pytest.fixture
    def store(self) -> VectorStore:
        s = VectorStore(":memory:", dimensions=4)
        yield s
        s.close()

    def test_insert_and_search(self, store):
        store.insert("kb_a", {"规则": "测试 A"}, [1.0, 0.0, 0.0, 0.0])
        store.insert("kb_b", {"规则": "测试 B"}, [0.0, 1.0, 0.0, 0.0])

        # cos distance ≈ 0 (identical) for kb_a
        results = store.search([1.0, 0.0, 0.0, 0.0], limit=2, threshold=2.0)
        assert len(results) >= 1
        assert results[0]["kb_id"] == "kb_a"

    def test_batch_insert(self, store):
        items = [
            ("k1", {"a": "1"}, [1.0, 0.0, 0.0, 0.0]),
            ("k2", {"b": "2"}, [0.0, 1.0, 0.0, 0.0]),
            ("k3", {"c": "3"}, [0.0, 0.0, 1.0, 0.0]),
        ]
        ids = store.insert_batch(items)
        assert len(ids) == 3

    def test_threshold_filter(self, store):
        store.insert("kb_a", {"规则": "A"}, [1.0, 0.0, 0.0, 0.0])

        # cos distance ≈ 2 (opposite)，threshold=0.5 应过滤掉
        results = store.search([-1.0, 0.0, 0.0, 0.0], limit=5, threshold=0.5)
        assert len(results) == 0

    def test_clear(self, store):
        store.insert("kb_a", {"x": "y"}, [1.0, 0.0, 0.0, 0.0])
        store.clear()
        results = store.search([1.0, 0.0, 0.0, 0.0], limit=5, threshold=2.0)
        assert len(results) == 0


class TestSearchResult:
    """SearchResult 数据类测试。"""

    def test_search_result_fields(self):
        entry = {"规则": "测试", "来源": "GB"}
        sr = SearchResult(kb_id="k1", kb_name="知识库1", kb_file="test.md", entry=entry, relevance=0.85)
        assert sr.kb_id == "k1"
        assert sr.kb_file == "test.md"
        assert sr.relevance == 0.85


class TestReviewPipeline:
    """审阅流水线测试。"""

    def test_pipeline_builds(self, kb_entries):
        """流水线应能正常构建。"""
        reg = make_registry_with_kbs(kb_entries)

        class MockDeps:
            kb_registry = reg
            model_provider = None

        pipeline = ReviewPipeline(MockDeps())
        graph = pipeline.build()
        assert graph is not None

    def test_parse_llm_response_yes_new_format(self):
        """新英文格式 + 结构化 reference。"""
        from agent_platform.agents.document_review.pipeline import _parse_llm_response

        response = '{"has_issue": "是", "error_reason": "禁用词", "suggestion": "改表述", "reference": {"kb_id": "compliance", "kb_file": "合规知识库", "content": "禁止使用..."}}'
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "是"
        assert result["content"]["error_reason"] == "禁用词"
        assert result["content"]["suggestion"] == "改表述"
        assert result["content"]["reference"]["kb_id"] == "compliance"
        assert result["content"]["reference"]["kb_file"] == "合规知识库"

    def test_parse_llm_response_no(self):
        from agent_platform.agents.document_review.pipeline import _parse_llm_response

        response = '{"has_issue": "否"}'
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "否"
        assert result["content"] == {}

    def test_parse_llm_response_with_markdown(self):
        from agent_platform.agents.document_review.pipeline import _parse_llm_response

        response = '```json\n{"has_issue": "否"}\n```'
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "否"

    def test_parse_llm_response_invalid(self):
        from agent_platform.agents.document_review.pipeline import _parse_llm_response

        response = "这不是有效的 JSON"
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "否"


class TestReviewTools:
    """审阅工具函数测试。"""

    def test_format_kb_results_empty(self):
        result = format_kb_results_for_prompt([])
        assert "无相关" in result

    def test_format_kb_results_with_data(self):
        data = [{"kb_id": "test", "kb_name": "测试", "kb_file": "test.md", "entry": {"规则": "必须使用法定单位", "来源": "GB"}, "relevance": 0.85}]
        result = format_kb_results_for_prompt(data)
        assert "test.md" in result
        assert "GB" in result
