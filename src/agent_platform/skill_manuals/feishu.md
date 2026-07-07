---
name: feishu
description: 飞书操作指南 —— 发送消息、操作文档、管理群组、机器人通知
keywords:
  - 飞书
  - Feishu
  - Lark
  - 消息
  - 机器人
  - 文档
  - 群组
  - 通知
  - webhook
---

# 飞书操作指南

## 发送消息（最常用）

### Webhook 机器人（推荐，无需 token）

```python
import requests
import json

WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"

def send_feishu_text(text: str):
    """发送纯文本消息"""
    payload = {
        "msg_type": "text",
        "content": {"text": text}
    }
    r = requests.post(WEBHOOK_URL, json=payload)
    r.raise_for_status()
    return r.json()

def send_feishu_card(title: str, content: str, color: str = "blue"):
    """发送卡片消息"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color
            },
            "elements": [
                {"tag": "markdown", "content": content}
            ]
        }
    }
    r = requests.post(WEBHOOK_URL, json=payload)
    r.raise_for_status()
    return r.json()
```

### 批量 @ 人

```python
def send_with_mentions(text: str, user_ids: list[str]):
    """发送消息并 @ 指定用户"""
    at_content = " ".join(f"<at user_id=\"{uid}\"></at>" for uid in user_ids)
    full_text = f"{at_content}\n{text}"
    payload = {
        "msg_type": "text",
        "content": {"text": full_text}
    }
    r = requests.post(WEBHOOK_URL, json=payload)
    r.raise_for_status()
```

## 创建飞书文档

```python
# 使用飞书开放平台 API（需要 tenant_access_token）
# 1. 获取 token
def get_tenant_token(app_id: str, app_secret: str) -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret}
    )
    return r.json()["tenant_access_token"]

# 2. 创建文档
def create_doc(title: str, content: str, token: str) -> str:
    r = requests.post(
        "https://open.feishu.cn/open-apis/docx/v1/documents",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"title": title}
    )
    doc_id = r.json()["data"]["document"]["document_id"]
    return f"https://bytedance.feishu.cn/docx/{doc_id}"
```

## 查询群组信息

```python
def list_groups(token: str, page_size: int = 20):
    r = requests.get(
        "https://open.feishu.cn/open-apis/chat/v4/list",
        headers={"Authorization": f"Bearer {token}"},
        params={"page_size": page_size}
    )
    return r.json()["data"]["groups"]

def get_group_members(token: str, chat_id: str):
    r = requests.get(
        f"https://open.feishu.cn/open-apis/im/v1/chats/{chat_id}/members",
        headers={"Authorization": f"Bearer {token}"}
    )
    return r.json()["data"]["items"]
```

## 上传文件

```python
def upload_file(file_path: str, token: str) -> str:
    import os
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    with open(file_path, "rb") as f:
        r = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/files",
            headers={"Authorization": f"Bearer {token}"},
            data={"file_name": file_name, "file_type": "stream"},
            files={"file": f}
        )
    return r.json()["data"]["file_key"]
```

## 注意事项

1. **Webhook URL 保密**：不要将 webhook URL 提交到代码仓库，使用环境变量
2. **消息频率限制**：单个 webhook 每分钟最多 20 条
3. **卡片消息**：比普通文本消息更丰富，支持按钮、图片、多列布局
4. **Token 有效期**：tenant_access_token 有效期 2 小时，需缓存并自动刷新
5. **企业内权限**：查询群组成员等操作需要应用在飞书后台开通相应权限
