from __future__ import annotations

_SCHEMAS: dict[str, str] = {
    "users": (
        "CREATE TABLE users (\n"
        "  id INT PRIMARY KEY,\n"
        "  name VARCHAR(100),\n"
        "  department VARCHAR(50),\n"
        "  hire_date DATE,\n"
        "  salary DECIMAL(10,2)\n"
        ");"
    ),
    "orders": (
        "CREATE TABLE orders (\n"
        "  id INT PRIMARY KEY,\n"
        "  user_id INT,\n"
        "  product_id INT,\n"
        "  amount DECIMAL(10,2),\n"
        "  status VARCHAR(20),\n"
        "  created_at TIMESTAMP\n"
        ");"
    ),
    "products": (
        "CREATE TABLE products (\n"
        "  id INT PRIMARY KEY,\n"
        "  name VARCHAR(200),\n"
        "  category VARCHAR(50),\n"
        "  price DECIMAL(10,2),\n"
        "  stock INT\n"
        ");"
    ),
}


def _validate_sql(sql: str) -> str | None:
    """校验 SQL 语句安全性。只允许单条 SELECT 查询。

    Returns:
        错误信息字符串，None 表示通过校验。
    """
    import re

    cleaned = sql.strip()

    # 移除单行注释
    cleaned = re.sub(r"--[^\n]*", "", cleaned)
    # 移除块注释
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

    # 检查多语句（分号前有实际内容）
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]
    if len(parts) > 1:
        return "错误：不允许执行多条 SQL 语句"

    first_word = cleaned.strip().upper().split()[0] if cleaned.strip().split() else ""
    if first_word != "SELECT":
        return f"错误：只允许执行 SELECT 查询，收到: {first_word}"

    return None


async def execute_sql(sql: str) -> list[dict[str, str]]:
    """执行 SQL 查询并返回结果行。

    TODO: 接入真实数据库连接池。
    """
    err = _validate_sql(sql)
    if err:
        return [{"error": err}]

    return [
        {"id": "1", "name": "示例数据", "value": "100"},
        {"id": "2", "name": "示例数据2", "value": "200"},
    ]


async def get_table_schema(table_name: str) -> str:
    """获取指定表的 DDL 定义。"""
    schema = _SCHEMAS.get(table_name)
    if schema:
        return schema
    return f"错误：未找到表 '{table_name}'。可用的表: {', '.join(_SCHEMAS.keys())}"
