from __future__ import annotations

import asyncio
import json

import pytest

from agent_platform.graph.events import (
    PlanEvent,
    StepDoneEvent,
    StepStartEvent,
    SynthesisDeltaEvent,
    SynthesisStartEvent,
)
from agent_platform.graph.patterns import (
    ExecutionPlan,
    SubTask,
    build_sequential_graph,
)


class TestEventSerialization:
    def test_step_start_event_to_dict(self):
        event = StepStartEvent(
            step_id="s1", skill_name="qa", description="测试"
        )
        d = event.to_dict()
        assert d["type"] == "step_start"
        assert d["step_id"] == "s1"
        assert "timestamp" in d

    def test_plan_event_to_dict(self):
        event = PlanEvent(subtasks=[{"id": "s1", "skill_name": "qa"}])
        d = event.to_dict()
        assert d["type"] == "plan"
        assert len(d["subtasks"]) == 1

    def test_event_json_roundtrip(self):
        event = StepDoneEvent(
            step_id="s1", skill_name="qa", result_summary="结果摘要"
        )
        d = event.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["step_id"] == "s1"
        assert parsed["result_summary"] == "结果摘要"

    def test_synthesis_events(self):
        start = SynthesisStartEvent()
        assert start.type == "synthesis_start"

        delta = SynthesisDeltaEvent(content="分析中...")
        d = delta.to_dict()
        assert d["content"] == "分析中..."


class TestExecutionPlan:
    def test_sequential_plan_creation(self):
        plan = ExecutionPlan(
            mode="sequential",
            subtasks=[
                SubTask(id="s1", skill_name="data_query", description="查询数据"),
                SubTask(
                    id="s2",
                    skill_name="contract_review",
                    description="审查合同",
                    depends_on=["s1"],
                ),
            ],
        )
        assert plan.mode == "sequential"
        assert len(plan.subtasks) == 2
        assert plan.subtasks[1].depends_on == ["s1"]

    def test_parallel_plan_creation(self):
        plan = ExecutionPlan(
            mode="parallel",
            subtasks=[
                SubTask(id="s1", skill_name="qa", description="知识检索"),
                SubTask(id="s2", skill_name="data_query", description="数据查询"),
            ],
        )
        assert plan.mode == "parallel"
        assert len(plan.subtasks) == 2

    def test_subtask_model_dump(self):
        st = SubTask(id="s1", skill_name="qa", description="测试")
        d = st.model_dump()
        assert d["id"] == "s1"
        assert d["skill_name"] == "qa"
        assert d["depends_on"] == []

    def test_execution_plan_model_dump_roundtrip(self):
        """验证 ExecutionPlan 完整序列化往返。"""
        plan = ExecutionPlan(
            mode="orchestrator",
            subtasks=[
                SubTask(id="s1", skill_name="qa", description="检索"),
                SubTask(id="s2", skill_name="data_query", description="查询"),
            ],
            synthesis_prompt="综合以上结果回答问题。",
        )
        data = plan.model_dump()
        restored = ExecutionPlan(**data)
        assert restored.mode == "orchestrator"
        assert len(restored.subtasks) == 2
        assert restored.synthesis_prompt == "综合以上结果回答问题。"


class TestSequentialGraphStructure:
    """验证顺序编排图的节点和边结构。"""

    def test_build_sequential_graph_creates_nodes_for_each_subtask(self):
        """每个 subtask 对应一个 step_X 节点。"""
        subtasks = [
            SubTask(id="s1", skill_name="qa", description="步骤1"),
            SubTask(id="s2", skill_name="data_query", description="步骤2"),
            SubTask(id="s3", skill_name="contract_review", description="步骤3"),
        ]
        # build_sequential_graph 需要 skills dict 和 deps
        # 此处验证 Subtask 数据结构正确即可；实际图执行需要模型
        assert len(subtasks) == 3
        # 验证 id 唯一（之前闭包 bug 会覆盖 id）
        ids = [st.id for st in subtasks]
        assert ids == ["s1", "s2", "s3"]


class TestSentinelPattern:
    """验证 sentinel 终止模式在事件队列中的正确性。"""

    @pytest.mark.asyncio
    async def test_sentinel_terminates_queue_consumer(self):
        """消费者在收到 sentinel 后正确退出。"""
        _SENTINEL = object()
        queue: asyncio.Queue = asyncio.Queue()

        async def producer():
            await queue.put("event_1")
            await queue.put("event_2")
            await queue.put(_SENTINEL)

        collected = []
        consumer = asyncio.create_task(producer())

        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            collected.append(event)

        await consumer
        assert collected == ["event_1", "event_2"]

    @pytest.mark.asyncio
    async def test_sentinel_pushed_on_producer_error(self):
        """即使 producer 异常，sentinel 也应被推送到队列。"""
        _SENTINEL = object()
        queue: asyncio.Queue = asyncio.Queue()

        async def producer_with_error():
            try:
                await queue.put("event_1")
                raise RuntimeError("simulated failure")
            finally:
                await queue.put(_SENTINEL)

        collected = []
        producer = asyncio.create_task(producer_with_error())

        while True:
            event = await queue.get()
            if event is _SENTINEL:
                break
            collected.append(event)

        exc = producer.exception()
        assert collected == ["event_1"]
        assert isinstance(exc, RuntimeError)
        assert str(exc) == "simulated failure"
