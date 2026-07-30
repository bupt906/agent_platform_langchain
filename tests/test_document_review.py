"""AI 文档审阅模块测试 — 外部知识库（万悟 hit 接口）版。"""

from __future__ import annotations

import json

import pytest

from agent_platform.agents.document_review.pipeline import (
    ReviewPipeline,
    _parse_llm_response,
    run_review_pipeline,
)
from agent_platform.agents.document_review.tools import (
    format_kb_results_for_prompt,
    parse_document,
    search_knowledge_bases,
    split_sentences,
)
from agent_platform.config.settings import Settings
from agent_platform.agents.document_review.knowledge_bases.client import KBHit, KnowledgeHitClient


# ── Fixtures ──────────────────────────────────────────────


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


class FakeResponse:
    """模拟 httpx.Response。"""

    def __init__(self, json_data: dict, status_code: int = 200):
        self._json = json_data
        self.status_code = status_code

    @property
    def text(self) -> str:
        import json

        return json.dumps(self._json, ensure_ascii=False)

    def json(self) -> dict:
        return self._json


class FakeHTTPClient:
    """模拟 httpx.AsyncClient，记录请求并按序返回预设响应。"""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.requests: list[dict] = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers})
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def make_hit_response(hits: list[tuple[str, str, str, float]]) -> dict:
    """构造 hit 接口响应。hits: [(knowledgeName, title, snippet, score), ...]"""
    return {
        "code": 0,
        "msg": "",
        "data": {
            "searchList": [
                {"title": t, "snippet": s, "knowledgeName": kn, "childContentList": [], "childScore": []}
                for kn, t, s, _ in hits
            ],
            "score": [score for _, _, _, score in hits],
            "useGraph": False,
        },
    }


class FakeKBClient:
    """模拟 KnowledgeHitClient。"""

    def __init__(self, hits: list[KBHit] | None = None, error: Exception | None = None):
        self._hits = hits or []
        self._error = error
        self.calls: list[tuple[list[str], str]] = []

    async def hit(self, kb_ids: list[str], question: str, retries: int = 1) -> list[KBHit]:
        self.calls.append((kb_ids, question))
        if self._error:
            raise self._error
        return self._hits


class FakeModel:
    def __init__(self, content: str):
        self._content = content

    async def ainvoke(self, messages):
        class R:
            pass

        r = R()
        r.content = self._content
        return r


class FakeModelProvider:
    def __init__(self, content: str = '{"has_issue": "否"}'):
        self._content = content

    def get_model(self, model_id=None):
        return FakeModel(self._content)


class FakeDeps:
    def __init__(self, kb_client=None, model_provider=None):
        self.kb_client = kb_client
        self.model_provider = model_provider


# ── 文档解析 ──────────────────────────────────────────────


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


# ── 句子切分 ──────────────────────────────────────────────


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


# ── 外部知识库客户端 ──────────────────────────────────────


class TestKnowledgeHitClient:
    """万悟 hit 接口客户端测试。"""

    def make_client(self, responses: list) -> tuple[KnowledgeHitClient, FakeHTTPClient]:
        http = FakeHTTPClient(responses)
        # 显式传入所有断言涉及的字段，避免依赖本机 .env / 环境变量
        settings = Settings(
            kb_api_base_url="http://kb.example.com",
            kb_api_key="test-key",
            kb_match_type="mix",
            kb_top_k=5,
            kb_threshold=0.4,
        )
        return KnowledgeHitClient(http, settings), http

    async def test_hit_builds_correct_request(self):
        client, http = self.make_client([FakeResponse(make_hit_response([]))])
        await client.hit(["kb1", "kb2"], "测试句子")

        req = http.requests[0]
        assert req["url"] == "http://kb.example.com/service/api/openapi/v1/knowledge/hit"
        assert req["headers"]["Authorization"] == "Bearer test-key"
        assert req["json"]["question"] == "测试句子"
        assert req["json"]["knowledgeList"] == [{"id": "kb1"}, {"id": "kb2"}]
        params = req["json"]["knowledgeMatchParams"]
        assert params["matchType"] == "mix"
        assert params["topK"] == 5
        assert params["threshold"] == 0.4

    async def test_hit_parses_response(self):
        resp = make_hit_response([
            ("2003716670903816193", "开票信息.docx", "公司名称：xxx", 0.6106349229812622),
        ])
        client, _ = self.make_client([FakeResponse(resp)])
        hits = await client.hit(["kb1"], "开票信息")

        assert len(hits) == 1
        # 单库请求：kb_id 取请求的知识库 id，而非响应的 knowledgeName
        assert hits[0].kb_id == "kb1"
        assert hits[0].kb_file == "开票信息.docx"
        assert hits[0].content == "公司名称：xxx"
        assert hits[0].relevance == 0.611

    async def test_hit_kb_id_matches_requested_in_multi_kb(self):
        """多库请求：knowledgeName 命中请求 id 则对应，否则回退 knowledgeName。"""
        resp = make_hit_response([
            ("kb2", "a.docx", "内容A", 0.9),       # knowledgeName ∈ 请求 → kb2
            ("unknown", "b.docx", "内容B", 0.8),   # 无法对应 → 回退 knowledgeName
        ])
        client, _ = self.make_client([FakeResponse(resp)])
        hits = await client.hit(["kb1", "kb2"], "测试")
        assert hits[0].kb_id == "kb2"
        assert hits[1].kb_id == "unknown"

    async def test_hit_sorts_by_relevance_desc(self):
        """命中结果按相关度降序排序（API 原始顺序可能乱序）。"""
        resp = make_hit_response([
            ("kn", "low.docx", "低相关", 0.42),
            ("kn", "high.docx", "高相关", 0.91),
            ("kn", "mid.docx", "中相关", 0.55),
        ])
        client, _ = self.make_client([FakeResponse(resp)])
        hits = await client.hit(["kb1"], "测试")
        assert [h.kb_file for h in hits] == ["high.docx", "mid.docx", "low.docx"]
        assert hits[0].relevance == 0.91

    async def test_hit_empty_result(self):
        client, _ = self.make_client([FakeResponse(make_hit_response([]))])
        hits = await client.hit(["kb1"], "无关内容")
        assert hits == []

    async def test_hit_business_error_no_retry(self):
        """业务错误（code != 0，如无效 kb_id）不可重试，1 次请求即抛。"""
        err = FakeResponse({"code": 500, "msg": "无效的知识库", "data": None})
        client, http = self.make_client([err, err])
        with pytest.raises(RuntimeError, match="知识库接口返回错误"):
            await client.hit(["kb1"], "测试")
        assert len(http.requests) == 1  # 不重试

    async def test_hit_4xx_no_retry(self):
        """HTTP 4xx（鉴权失败等）不可重试，1 次请求即抛。"""
        err = FakeResponse({"msg": "unauthorized"}, status_code=401)
        client, http = self.make_client([err, err])
        with pytest.raises(RuntimeError, match="请求被拒绝"):
            await client.hit(["kb1"], "测试")
        assert len(http.requests) == 1  # 不重试

    async def test_hit_5xx_retries(self):
        """HTTP 5xx 可重试，重试后仍失败则抛出。"""
        err = FakeResponse({"msg": "gateway error"}, status_code=502)
        client, http = self.make_client([err, err])
        with pytest.raises(RuntimeError, match="知识库检索失败"):
            await client.hit(["kb1"], "测试")
        assert len(http.requests) == 2  # 重试了 1 次

    async def test_hit_3xx_retries_with_status_in_error(self):
        """HTTP 3xx（重定向，通常是 base_url 配置错误）可重试，错误信息保留状态码。"""
        err = FakeResponse({}, status_code=302)
        client, http = self.make_client([err, err])
        with pytest.raises(RuntimeError, match="HTTP 302"):
            await client.hit(["kb1"], "测试")
        assert len(http.requests) == 2

    async def test_hit_non_dict_json_retries(self):
        """响应是合法 JSON 但非对象（如网关返回字符串）→ 按畸形响应重试。"""
        bad = FakeResponse("upstream timeout")  # .json() 返回字符串
        ok = FakeResponse(make_hit_response([("kn", "f.md", "内容", 0.9)]))
        client, http = self.make_client([bad, ok])
        hits = await client.hit(["kb1"], "测试")
        assert len(hits) == 1
        assert len(http.requests) == 2

    async def test_hit_retry_succeeds_on_second_attempt(self):
        ok = FakeResponse(make_hit_response([("kn", "f.md", "内容", 0.9)]))
        client, http = self.make_client([ConnectionError("网络错误"), ok])
        hits = await client.hit(["kb1"], "测试")
        assert len(hits) == 1
        assert len(http.requests) == 2


# ── 聊天入口依赖注入 ──────────────────────────────────────


class TestSkillDepsInjection:
    """回归测试：app.py 的注入方式必须能被 review_document 工具路径读到。

    背景：document_review/__init__.py 把包属性 skill 绑定为 DocumentReviewSkill
    实例（遮蔽 skill 子模块），app.py `from ... import skill` 拿到的是实例，
    因此 _deps 必须是实例/类属性，模块级全局注入会失效。
    """

    async def test_deps_injection_reaches_review_path(self, sample_txt_file):
        # 与 api/app.py 完全相同的导入与注入方式
        from agent_platform.agents.document_review import skill as injected

        old = injected._deps
        try:
            injected._deps = FakeDeps(
                kb_client=FakeKBClient(hits=[]), model_provider=FakeModelProvider()
            )
            out = json.loads(await injected._run_review(sample_txt_file, "kb1"))
            assert out["summary"]["total_sentences"] == 3
            assert out["summary"]["errors"] == 0  # deps 生效，未走 kb_client 缺失分支
        finally:
            injected._deps = old

    async def test_without_injection_marks_errors(self, sample_txt_file):
        """未注入 deps 时不崩溃：所有句子标记 error，任务仍能完成。"""
        from agent_platform.agents.document_review.skill import DocumentReviewSkill

        sk = DocumentReviewSkill()
        assert sk._deps is None  # 新实例默认未注入
        out = json.loads(await sk._run_review(sample_txt_file, "kb1"))
        assert out["summary"]["total_sentences"] == 3
        assert out["summary"]["errors"] == 3


# ── 审阅工具函数 ──────────────────────────────────────────


class TestReviewTools:
    """审阅工具函数测试。"""

    async def test_search_knowledge_bases(self):
        fake = FakeKBClient(hits=[KBHit(kb_id="k1", kb_file="a.docx", content="条文内容", relevance=0.85)])
        results = await search_knowledge_bases(["k1"], "测试句子", fake)
        assert results == [{"kb_id": "k1", "kb_file": "a.docx", "content": "条文内容", "relevance": 0.85}]
        assert fake.calls == [(["k1"], "测试句子")]

    def test_format_kb_results_empty(self):
        result = format_kb_results_for_prompt([])
        assert "无相关" in result

    def test_format_kb_results_with_data(self):
        data = [{"kb_id": "test", "kb_file": "test.docx", "content": "必须使用法定单位", "relevance": 0.85}]
        result = format_kb_results_for_prompt(data)
        assert "test.docx" in result
        assert "必须使用法定单位" in result
        assert "0.85" in result


# ── 审阅流水线 ────────────────────────────────────────────


class TestReviewPipeline:
    """审阅流水线测试。"""

    def test_pipeline_builds(self):
        """流水线应能正常构建。"""
        pipeline = ReviewPipeline(FakeDeps(kb_client=FakeKBClient()))
        graph = pipeline.build()
        assert graph is not None

    async def test_run_pipeline_no_hits(self, sample_txt_file):
        """检索无结果 → 全部判无问题。"""
        deps = FakeDeps(kb_client=FakeKBClient(hits=[]), model_provider=FakeModelProvider())
        result = await run_review_pipeline(sample_txt_file, ["kb1"], deps, task_id=7)

        assert result["summary"]["total_sentences"] == 3
        assert result["summary"]["issues_found"] == 0
        assert all(r["has_issue"] == "否" for r in result["results"])
        assert all(r["task_id"] == 7 for r in result["results"])

    async def test_run_pipeline_with_issue(self, sample_txt_file):
        """检索有结果 + LLM 判有问题。"""
        hits = [KBHit(kb_id="kb1", kb_file="规范.docx", content="禁止使用绝对化用语", relevance=0.9)]
        llm_response = (
            '{"has_issue": "是", "error_reason": "使用绝对化用语", "suggestion": "改为相对表述", '
            '"reference": {"kb_id": "kb1", "kb_file": "规范.docx", "content": "禁止使用绝对化用语"}}'
        )
        deps = FakeDeps(kb_client=FakeKBClient(hits=hits), model_provider=FakeModelProvider(llm_response))
        result = await run_review_pipeline(sample_txt_file, ["kb1"], deps)

        assert result["summary"]["issues_found"] == 3
        first = result["results"][0]
        assert first["has_issue"] == "是"
        assert first["content"]["reference"]["kb_file"] == "规范.docx"

    async def test_run_pipeline_kb_error_marks_error(self, sample_txt_file):
        """检索失败（重试后）→ 该句标记 error，任务不中断。"""
        deps = FakeDeps(
            kb_client=FakeKBClient(error=RuntimeError("平台不可用")),
            model_provider=FakeModelProvider(),
        )
        result = await run_review_pipeline(sample_txt_file, ["kb1"], deps)

        assert result["summary"]["total_sentences"] == 3
        assert result["summary"]["errors"] == 3
        assert all(r["error"] for r in result["results"])
        assert all(r["has_issue"] == "否" for r in result["results"])

    async def test_run_pipeline_no_kb_client(self, sample_txt_file):
        """kb_client 未初始化 → 全部标记 error。"""
        deps = FakeDeps(kb_client=None, model_provider=FakeModelProvider())
        result = await run_review_pipeline(sample_txt_file, ["kb1"], deps)
        assert result["summary"]["errors"] == 3

    def test_parse_llm_response_yes_new_format(self):
        """结构化 reference 解析。"""
        response = '{"has_issue": "是", "error_reason": "禁用词", "suggestion": "改表述", "reference": {"kb_id": "compliance", "kb_file": "合规知识库", "content": "禁止使用..."}}'
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "是"
        assert result["content"]["error_reason"] == "禁用词"
        assert result["content"]["suggestion"] == "改表述"
        assert result["content"]["reference"]["kb_id"] == "compliance"
        assert result["content"]["reference"]["kb_file"] == "合规知识库"

    def test_parse_llm_response_no(self):
        response = '{"has_issue": "否"}'
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "否"
        assert result["content"] == {}

    def test_parse_llm_response_with_markdown(self):
        response = '```json\n{"has_issue": "否"}\n```'
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "否"

    def test_parse_llm_response_invalid(self):
        response = "这不是有效的 JSON"
        result = _parse_llm_response(response, "测试句子")
        assert result["has_issue"] == "否"
