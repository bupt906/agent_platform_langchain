"""知识库能力模块测试。

覆盖三件事：后端选择（迁移开关）、ID 映射（迁移期兼容），以及工具层最要紧的一条
约定——检索失败必须让模型看见，绝不能伪装成「没有找到」。
"""

from __future__ import annotations

import pytest

from agent_platform.config.settings import (
    OmniMindKnowledgeConfig,
    Settings,
    WanwuKnowledgeConfig,
)
from agent_platform.knowledge import build_provider
from agent_platform.knowledge.models import (
    KBAnswer,
    KBDocument,
    KBHit,
    KBInfo,
    KBIngestResult,
    KBSearchResult,
)
from agent_platform.knowledge.provider import (
    KnowledgeConfigError,
    KnowledgeProvider,
    KnowledgeUnavailable,
)
from agent_platform.knowledge.providers.dual import DualProvider
from agent_platform.knowledge.providers.omnimind import parse_kb_id_map
from agent_platform.knowledge.providers.wanwu import WanwuProvider
from agent_platform.tools import registry
from agent_platform.tools.knowledge_tools import register_knowledge_tools


class StubProvider(KnowledgeProvider):
    """可编程的假后端。"""

    name = "stub"

    def __init__(
        self, hits=None, degraded=None, error=None, kbs=None, answer=None,
        document=None, ingest=None,
    ):
        self._hits = hits or []
        self._degraded = degraded or []
        self._error = error
        self._kbs = kbs or []
        self._answer = answer
        self._document = document
        self._ingest = ingest
        self.calls: list[tuple[list[str], str, int | None]] = []
        self.ingested: list[tuple[str, str, bytes]] = []

    async def search(self, kb_ids, query, *, top_k=None) -> KBSearchResult:
        self.calls.append((kb_ids, query, top_k))
        if self._error:
            raise self._error
        return KBSearchResult(hits=self._hits, degraded=self._degraded)

    async def list_kbs(self) -> list[KBInfo]:
        if self._error:
            raise self._error
        return self._kbs

    async def answer(self, question, kb_ids, *, top_k=None) -> KBAnswer:
        if self._error:
            raise self._error
        return self._answer

    async def fetch_document(self, doc_id) -> KBDocument:
        if self._error:
            raise self._error
        return self._document

    async def ingest_document(self, kb_id, filename, content, *, content_type="") -> KBIngestResult:
        self.ingested.append((kb_id, filename, content))
        if self._error:
            raise self._error
        return self._ingest


@pytest.fixture(autouse=True)
def clean_registry():
    """工具注册表是模块级全局，测试之间必须隔离。"""
    saved = registry.tool_map()
    registry._registry.clear()
    yield
    registry._registry.clear()
    registry._registry.update(saved)


def a_hit(**kwargs) -> KBHit:
    base = {"kb_id": "kb-1", "kb_file": "标准.docx", "content": "必须使用法定计量单位", "relevance": 0.9}
    return KBHit(**{**base, **kwargs})


# ── 后端选择：迁移开关 ────────────────────────────────────


class TestProviderSelection:
    def test_default_is_wanwu(self):
        settings = Settings(knowledge_provider="wanwu")
        provider = build_provider(http_client=object(), settings=settings)
        assert isinstance(provider, WanwuProvider)
        assert provider.name == "wanwu"

    def test_dual_wraps_both_backends(self):
        settings = Settings(
            knowledge_provider="dual",
            omnimind=OmniMindKnowledgeConfig(base_url="http://kb:8000", api_key="k"),
            wanwu=WanwuKnowledgeConfig(base_url="http://wanwu:8081"),
        )
        provider = build_provider(http_client=None, settings=settings)
        assert isinstance(provider, DualProvider)

    def test_unknown_backend_fails_loudly(self):
        settings = Settings(knowledge_provider="nope")
        with pytest.raises(KnowledgeConfigError, match="未知的知识库后端"):
            build_provider(http_client=object(), settings=settings)

    def test_switching_backend_needs_only_configuration(self):
        """迁移的核心主张：换后端只改一个配置项，调用方类型不变。"""
        wanwu = build_provider(object(), Settings(knowledge_provider="wanwu"))
        omnimind = build_provider(
            None,
            Settings(
                knowledge_provider="omnimind",
                omnimind=OmniMindKnowledgeConfig(base_url="http://kb:8000", api_key="k"),
            ),
        )
        assert isinstance(wanwu, KnowledgeProvider)
        assert isinstance(omnimind, KnowledgeProvider)
        assert {wanwu.name, omnimind.name} == {"wanwu", "omnimind"}


# ── 迁移期的知识库 ID 映射 ────────────────────────────────


class TestKBIdMapping:
    def test_parses_pairs(self):
        assert parse_kb_id_map("2003716670903816192:a3f2-uuid, 999:bbb") == {
            "2003716670903816192": "a3f2-uuid",
            "999": "bbb",
        }

    def test_empty_is_empty(self):
        assert parse_kb_id_map("") == {}

    def test_malformed_entry_is_rejected(self):
        with pytest.raises(KnowledgeConfigError, match="旧id:新id"):
            parse_kb_id_map("no-colon-here")


# ── 工具层：失败必须让模型看见 ────────────────────────────


class TestKnowledgeTools:
    def tools(self, provider) -> dict:
        register_knowledge_tools(provider)
        return registry.tool_map()

    def test_registers_the_full_toolset_for_every_agent(self):
        names = set(self.tools(StubProvider()))
        assert names == {
            "search_knowledge",
            "answer_from_knowledge",
            "list_knowledge_bases",
            "fetch_knowledge_document",
            "add_to_knowledge_base",
        }

    async def test_search_returns_formatted_evidence(self):
        tools = self.tools(StubProvider(hits=[a_hit(), a_hit(kb_file="规范.pdf", relevance=0.7)]))
        out = await tools["search_knowledge"].ainvoke({"query": "计量单位", "kb_ids": "kb-1"})

        assert "证据 1" in out and "证据 2" in out
        assert "标准.docx" in out and "规范.pdf" in out
        assert "必须使用法定计量单位" in out

    async def test_search_failure_is_not_disguised_as_no_results(self):
        """检索失败和「知识库里没有」必须是两种不同的信号。"""
        tools = self.tools(StubProvider(error=KnowledgeUnavailable("知识库中台不可达")))
        out = await tools["search_knowledge"].ainvoke({"query": "计量单位"})

        assert "失败" in out
        assert "知识库中台不可达" in out
        assert "不表示知识库中没有相关内容" in out
        assert "未检索到相关内容" not in out

    async def test_empty_result_says_not_found(self):
        tools = self.tools(StubProvider(hits=[]))
        out = await tools["search_knowledge"].ainvoke({"query": "计量单位"})

        assert "未检索到相关内容" in out
        assert "失败" not in out

    async def test_degraded_backend_is_surfaced_to_the_model(self):
        """降级必须显式告知，否则模型会把不完整的召回当作完整证据。"""
        tools = self.tools(StubProvider(hits=[a_hit()], degraded=["milvus", "reranker"]))
        out = await tools["search_knowledge"].ainvoke({"query": "计量单位"})

        assert "检索能力不完整" in out
        assert "milvus" in out and "reranker" in out
        assert "不要据此断定知识库中没有相关内容" in out

    async def test_empty_and_degraded_reports_both(self):
        tools = self.tools(StubProvider(hits=[], degraded=["elasticsearch"]))
        out = await tools["search_knowledge"].ainvoke({"query": "计量单位"})

        assert "未检索到相关内容" in out
        assert "检索能力不完整" in out

    async def test_kb_ids_are_parsed_from_comma_string(self):
        provider = StubProvider(hits=[])
        tools = self.tools(provider)
        await tools["search_knowledge"].ainvoke({"query": "q", "kb_ids": " kb-1 , kb-2 ,"})

        assert provider.calls[0][0] == ["kb-1", "kb-2"]

    async def test_blank_kb_ids_means_all_authorized(self):
        provider = StubProvider(hits=[])
        tools = self.tools(provider)
        await tools["search_knowledge"].ainvoke({"query": "q"})

        assert provider.calls[0][0] == []

    async def test_answer_tool_reports_sources(self):
        answer = KBAnswer(
            answer="应立即停机。",
            citations=[a_hit(kb_file="操作规程.docx")],
            model="deepseek-chat",
            grounded=True,
        )
        tools = self.tools(StubProvider(answer=answer))
        out = await tools["answer_from_knowledge"].ainvoke({"question": "振动超标怎么办"})

        assert "应立即停机。" in out
        assert "操作规程.docx" in out

    async def test_answer_tool_admits_when_ungrounded(self):
        tools = self.tools(StubProvider(answer=KBAnswer(answer="", grounded=False)))
        out = await tools["answer_from_knowledge"].ainvoke({"question": "无关问题"})

        assert "没有找到足以回答该问题的证据" in out

    async def test_answer_tool_surfaces_backend_without_server_side_rag(self):
        """万悟后端不支持服务端问答，工具必须如实说明而不是编造答案。"""
        provider = WanwuProvider(None, WanwuKnowledgeConfig())
        tools = self.tools(provider)
        out = await tools["answer_from_knowledge"].ainvoke({"question": "问题"})

        assert "失败" in out
        assert "不支持服务端问答" in out

    async def test_list_kbs_helps_agent_choose_scope(self):
        tools = self.tools(
            StubProvider(kbs=[KBInfo(kb_id="kb-1", name="安全规程", document_count=12)])
        )
        out = await tools["list_knowledge_bases"].ainvoke({})

        assert "安全规程" in out and "kb-1" in out and "12" in out

    async def test_list_kbs_explains_backends_without_a_catalog(self):
        tools = self.tools(WanwuProvider(None, WanwuKnowledgeConfig()))
        out = await tools["list_knowledge_bases"].ainvoke({})

        assert "不提供知识库清单" in out


class TestKnowledgeWriteTools:
    def tools(self, provider) -> dict:
        register_knowledge_tools(provider)
        return registry.tool_map()

    async def test_fetch_document_returns_full_text(self):
        doc = KBDocument(doc_id="d1", title="操作规程.docx", text="第一条…\n第二条…", chunk_count=2)
        tools = self.tools(StubProvider(document=doc))
        out = await tools["fetch_knowledge_document"].ainvoke({"doc_id": "d1"})

        assert "操作规程.docx" in out
        assert "第一条" in out and "第二条" in out
        assert "截断" not in out

    async def test_fetch_document_flags_truncation(self):
        doc = KBDocument(doc_id="d1", title="长文.docx", text="正文", truncated=True)
        tools = self.tools(StubProvider(document=doc))
        out = await tools["fetch_knowledge_document"].ainvoke({"doc_id": "d1"})

        assert "截断" in out

    async def test_ingest_reports_queued_when_exempted(self):
        result = KBIngestResult(
            doc_id="new-1", title="总结.md", parse_status="pending",
            queued=True, review_required=False,
        )
        provider = StubProvider(ingest=result)
        tools = self.tools(provider)
        out = await tools["add_to_knowledge_base"].ainvoke(
            {"kb_id": "kb-1", "filename": "总结.md", "content": "结论正文"}
        )

        assert provider.ingested == [("kb-1", "总结.md", "结论正文".encode())]
        assert "已写入知识库并进入解析队列" in out
        assert "new-1" in out

    async def test_ingest_tells_the_model_when_a_human_must_approve(self):
        """待审不等于写入成功，模型不能据此说「已入库可检索」。"""
        result = KBIngestResult(
            doc_id="new-2", title="敏感.md", parse_status="review",
            queued=False, review_required=True, audit_risk_level="high",
        )
        tools = self.tools(StubProvider(ingest=result))
        out = await tools["add_to_knowledge_base"].ainvoke(
            {"kb_id": "kb-1", "filename": "敏感.md", "content": "x"}
        )

        assert "需要管理员" in out and "放行" in out
        assert "high" in out

    async def test_ingest_failure_is_reported(self):
        tools = self.tools(StubProvider(error=KnowledgeUnavailable("中台不可达"), ingest=None))
        out = await tools["add_to_knowledge_base"].ainvoke(
            {"kb_id": "kb-1", "filename": "a.md", "content": "x"}
        )

        assert "写入知识库失败" in out and "中台不可达" in out

    async def test_backends_without_write_support_say_so(self):
        from agent_platform.config.settings import WanwuKnowledgeConfig
        from agent_platform.knowledge.providers.wanwu import WanwuProvider

        tools = self.tools(WanwuProvider(None, WanwuKnowledgeConfig()))
        out = await tools["add_to_knowledge_base"].ainvoke(
            {"kb_id": "kb-1", "filename": "a.md", "content": "x"}
        )

        assert "不支持写入知识库" in out


# ── 任何 Agent / Skill 都能按名字绑定 ─────────────────────


class TestToolsAreAvailableToEveryAgent:
    async def test_declarative_skill_can_bind_knowledge_tools_by_name(self):
        """声明式 Skill 只写工具名就能拿到知识库能力——这是本次改造的目标。"""
        from agent_platform.skills.builder import resolve_skill_tools
        from agent_platform.skills.registry import DeclarativeSkill

        register_knowledge_tools(StubProvider())
        skill = DeclarativeSkill(
            name="demo",
            description="示例",
            tools=["search_knowledge", "list_knowledge_bases"],
        )
        bound = resolve_skill_tools(skill, registry.tool_map())

        assert [tool.name for tool in bound] == ["search_knowledge", "list_knowledge_bases"]

    async def test_code_agent_can_pull_knowledge_tools_from_registry(self):
        register_knowledge_tools(StubProvider())
        bound = registry.get_many(["search_knowledge"])

        assert [tool.name for tool in bound] == ["search_knowledge"]


# ── 双跑比对 ──────────────────────────────────────────────


class TestDualProvider:
    async def test_returns_primary_results(self):
        primary = StubProvider(hits=[a_hit(kb_file="主.docx")])
        shadow = StubProvider(hits=[a_hit(kb_file="影子.docx")])
        result = await DualProvider(primary, shadow).search(["kb-1"], "q")

        assert [hit.kb_file for hit in result.hits] == ["主.docx"]
        assert shadow.calls, "影子后端也应被调用，否则比不出差异"

    async def test_shadow_failure_does_not_affect_caller(self):
        primary = StubProvider(hits=[a_hit()])
        shadow = StubProvider(error=KnowledgeUnavailable("影子挂了"))
        result = await DualProvider(primary, shadow).search(["kb-1"], "q")

        assert len(result.hits) == 1

    async def test_writes_go_only_to_the_primary_backend(self):
        """影子后端是观测手段，不该产生副作用。"""
        primary = StubProvider(ingest=KBIngestResult(doc_id="d", title="a.md"))
        shadow = StubProvider(ingest=KBIngestResult(doc_id="x", title="a.md"))
        await DualProvider(primary, shadow).ingest_document("kb-1", "a.md", b"x")

        assert primary.ingested and not shadow.ingested

    async def test_primary_failure_still_fails(self):
        """主后端失败就是失败，不能用影子结果顶替——那会掩盖迁移目标的真实可用性。"""
        primary = StubProvider(error=KnowledgeUnavailable("主挂了"))
        shadow = StubProvider(hits=[a_hit()])

        with pytest.raises(KnowledgeUnavailable, match="主挂了"):
            await DualProvider(primary, shadow).search(["kb-1"], "q")
