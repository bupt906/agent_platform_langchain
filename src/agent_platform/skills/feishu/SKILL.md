---
name: feishu
description: 飞书操作。用户需要发送飞书消息、操作文档、管理群组、发送机器人通知时使用。
tools: [execute_python]
complete_tool: complete_task
---

# 飞书操作指南

## 发送消息

### Webhook 机器人（推荐）

```python
import requests

WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"

def send_text(text: str):
    payload = {"msg_type": "text", "content": {"text": text}}
    r = requests.post(WEBHOOK_URL, json=payload)
    r.raise_for_status()
    return r.json()

def send_card(title: str, content: str, color: str = "blue"):
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}, "template": color},
            "elements": [{"tag": "markdown", "content": content}]
        }
    }
    r = requests.post(WEBHOOK_URL, json=payload)
    r.raise_for_status()
    return r.json()
```

### 批量 @ 人

```python
def send_with_mentions(text: str, user_ids: list[str]):
    at_content = " ".join(f'<at user_id="{uid}"></at>' for uid in user_ids)
    payload = {"msg_type": "text", "content": {"text": f"{at_content}\n{text}"}}
    r = requests.post(WEBHOOK_URL, json=payload)
    r.raise_for_status()
```

## 创建飞书文档

```python
def get_tenant_token(app_id: str, app_secret: str) -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret}
    )
    return r.json()["tenant_access_token"]

def create_doc(title: str, token: str) -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/docx/v1/documents",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"title": title}
    )
    doc_id = r.json()["data"]["document"]["document_id"]
    return f"https://bytedance.feishu.cn/docx/{doc_id}"
```

## 注意事项

1. **Webhook URL 保密**: 使用环境变量，不要硬编码
2. **消息频率限制**: 单个 webhook 每分钟最多 20 条
3. **Token 有效期**: tenant_access_token 有效期 2 小时，需缓存
4. **权限**: 查询群组成员等操作需在飞书后台开通权限
