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


async def execute_sql(sql: str) -> list[dict[str, str]]:
    """执行 SQL 查询并返回结果行。

    TODO: 接入真实数据库连接池。
    """
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
