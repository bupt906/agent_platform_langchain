"""技能手册系统测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_platform.skill_manuals.loader import SkillManual, SkillManualRegistry


# ── 示例手册 ──────────────────────────────────────────────────

_PPT_MD = """---
name: ppt
description: PowerPoint 操作指南
keywords: [PPT, PowerPoint, 幻灯片]
---

# PPT 操作指南

## 创建幻灯片
使用 python-pptx 库。
"""

_FEISHU_MD = """---
name: feishu
description: 飞书操作指南
keywords: [飞书, Feishu, 消息, 通知]
---

# 飞书操作指南

## 发送消息
使用 Webhook 机器人。
"""

_PDF_MD = """---
name: pdf
description: PDF 操作指南
keywords: [PDF, 导出, 打印]
---

# PDF 操作指南

## 生成 PDF
使用 weasyprint 或 reportlab。
"""

_NO_FRONTMATTER_MD = """# 无元数据手册

这是没有 frontmatter 的手册正文。
"""


# ── Fixture ────────────────────────────────────────────────────


@pytest.fixture
def manuals_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        (base / "ppt.md").write_text(_PPT_MD, encoding="utf-8")
        (base / "feishu.md").write_text(_FEISHU_MD, encoding="utf-8")
        (base / "pdf.md").write_text(_PDF_MD, encoding="utf-8")
        (base / "no_meta.md").write_text(_NO_FRONTMATTER_MD, encoding="utf-8")
        yield base


# ── 测试 ──────────────────────────────────────────────────────


class TestSkillManualRegistry:
    def test_load_from_dir(self, manuals_dir):
        registry = SkillManualRegistry()
        count = registry.load_from_dir(manuals_dir)
        assert count == 4
        assert registry.count == 4

    def test_get_manual(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        ppt = registry.get("ppt")
        assert ppt is not None
        assert ppt.name == "ppt"
        assert "PowerPoint 操作指南" in ppt.description
        assert "PPT" in ppt.keywords
        assert "python-pptx" in ppt.content

    def test_get_nonexistent(self):
        registry = SkillManualRegistry()
        assert registry.get("nonexistent") is None

    def test_list_infos(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        infos = registry.list_infos()
        assert len(infos) == 4
        names = {i["name"] for i in infos}
        assert names == {"ppt", "feishu", "pdf", "no_meta"}

    def test_register_and_unregister(self):
        registry = SkillManualRegistry()
        manual = SkillManual(name="test", description="测试", keywords=["测试"], content="正文")
        registry.register(manual)
        assert registry.count == 1
        assert registry.get("test") is not None

        registry.unregister("test")
        assert registry.count == 0
        assert registry.unregister("nonexistent") is False

    def test_no_frontmatter_uses_filename(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        manual = registry.get("no_meta")
        assert manual is not None
        assert manual.name == "no_meta"
        assert len(manual.keywords) == 0
        assert "无元数据手册" in manual.content


class TestManualMatching:
    def test_exact_keyword_match(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        matched = registry.match("帮我做个PPT演示文稿")
        assert matched is not None
        assert matched.name == "ppt"

    def test_feishu_match(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        matched = registry.match("用飞书发一条通知消息")
        assert matched is not None
        assert matched.name == "feishu"

    def test_pdf_match(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        matched = registry.match("把这个导出成PDF")
        assert matched is not None
        assert matched.name == "pdf"

    def test_no_match(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        matched = registry.match("今天天气怎么样")
        assert matched is None

    def test_multiple_keywords_choose_highest_score(self, manuals_dir):
        """'幻灯片' 既可能匹配 PPT，但如果 query 也包含飞书关键词，应优先匹配飞书"""
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        # 只有 PDF 关键词
        matched = registry.match("把报告打印出来")
        assert matched is not None
        assert matched.name == "pdf"


class TestGetPromptText:
    def test_returns_formatted_prompt(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        prompt = registry.get_prompt_text("帮我做一个PPT")
        assert prompt is not None
        assert "操作指南: ppt" in prompt
        assert "PowerPoint 操作指南" in prompt
        assert "python-pptx" in prompt

    def test_by_exact_name(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        prompt = registry.get_prompt_text("feishu")
        assert prompt is not None
        assert "飞书操作指南" in prompt

    def test_no_match_returns_none(self, manuals_dir):
        registry = SkillManualRegistry()
        registry.load_from_dir(manuals_dir)

        prompt = registry.get_prompt_text("今天天气")
        assert prompt is None
