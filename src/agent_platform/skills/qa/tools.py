from __future__ import annotations


async def knowledge_search(query: str, top_k: int = 5) -> list[dict[str, str]]:
    """从向量数据库中检索相关文档。

    TODO: 接入 Milvus / Elasticsearch 等真实向量检索引擎。
    """
    mock_results = [
        {
            "content": f"关于「{query}」的知识库文档内容片段 1 ...",
            "source": "知识库-制度文档-001",
            "score": "0.95",
        },
        {
            "content": f"关于「{query}」的知识库文档内容片段 2 ...",
            "source": "知识库-FAQ-042",
            "score": "0.90",
        },
        {
            "content": f"关于「{query}」的知识库文档内容片段 3 ...",
            "source": "知识库-操作手册-007",
            "score": "0.85",
        },
    ]
    return mock_results[:top_k]
