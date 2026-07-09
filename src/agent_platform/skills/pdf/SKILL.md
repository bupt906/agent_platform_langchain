---
name: pdf
description: PDF 操作。用户需要读取、生成、合并、拆分、填写 PDF 表单时使用。
tools: [execute_python]
complete_tool: complete_task
---

# PDF 操作指南

## 工具选择

| 场景 | 工具 | 安装 |
|------|------|------|
| 读取文本 | `pymupdf` (fitz) | `pip install pymupdf` |
| HTML → PDF | `weasyprint` | `pip install weasyprint` |
| 创建生成 | `reportlab` | `pip install reportlab` |
| 合并/拆分 | `pymupdf` | 一个库解决 |
| 表单填写 | `pypdf` | `pip install pypdf` |

## 读取 PDF

```python
import fitz

doc = fitz.open("document.pdf")
full_text = ""
for page in doc:
    full_text += page.get_text()
doc.close()
```

## HTML → PDF（最灵活）

```python
from weasyprint import HTML

HTML(string="<h1>Hello</h1><p>内容...</p>").write_pdf("output.pdf")
```

## Markdown → PDF

```python
import markdown
from weasyprint import HTML

with open("readme.md") as f:
    md = f.read()
html = markdown.markdown(md, extensions=["tables", "fenced_code"])
HTML(string=f"<html><body>{html}</body></html>").write_pdf("output.pdf")
```

## 合并 PDF

```python
import fitz

merged = fitz.open()
for f in ["a.pdf", "b.pdf"]:
    doc = fitz.open(f)
    merged.insert_pdf(doc)
    doc.close()
merged.save("merged.pdf")
merged.close()
```

## 拆分 PDF

```python
import fitz

doc = fitz.open("input.pdf")
for i, page in enumerate(doc):
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=i, to_page=i)
    new_doc.save(f"page_{i+1}.pdf")
    new_doc.close()
doc.close()
```

## 注意事项

1. **中文字体**: ReportLab 必须注册 TTF 字体才能显示中文
2. **weasyprint 依赖**: Linux 需要 `libpango` 系统库，macOS 无需额外安装
3. **大文件**: `pymupdf` 比 `pypdf` 快 10 倍以上
4. **扫描件 OCR**: 纯扫描件需用 `pytesseract` + `pdf2image`
