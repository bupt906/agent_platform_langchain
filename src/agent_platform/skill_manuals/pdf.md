---
name: pdf
description: PDF 操作指南 —— 读取、提取、生成、合并、填写表单
keywords:
  - PDF
  - pdf
  - 导出
  - 打印
  - 表单
  - 合并
  - 拆分
---

# PDF 操作指南

## 工具选择

| 场景 | 推荐工具 | 安装 |
|------|---------|------|
| 读取文本 | `pymupdf` (fitz) | `pip install pymupdf` |
| 创建/生成 | `reportlab` | `pip install reportlab` |
| HTML → PDF | `weasyprint` | `pip install weasyprint` |
| 表单填写 | `pypdf` | `pip install pypdf` |
| 合并/拆分 | `pymupdf` | 一个库解决 |

## 读取 PDF

### 提取全部文字

```python
import fitz  # pymupdf

doc = fitz.open("document.pdf")
full_text = ""
for page in doc:
    full_text += page.get_text()
doc.close()
```

### 提取指定页面

```python
doc = fitz.open("document.pdf")
page = doc[2]  # 第 3 页（0-indexed）
text = page.get_text()
```

### 提取表格

```python
page = doc[0]
tables = page.find_tables()
for table in tables:
    df = table.to_pandas()  # 需要 pandas
```

## 生成 PDF

### HTML → PDF（最灵活）

```python
from weasyprint import HTML

HTML(string="<h1>Hello</h1><p>内容...</p>").write_pdf("output.pdf")
HTML(filename="template.html").write_pdf("output.pdf")
```

### 用 ReportLab 编程式生成

```python
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# 注册中文字体
pdfmetrics.registerFont(TTFont("SimSun", "SimSun.ttf"))

c = canvas.Canvas("output.pdf", pagesize=A4)
c.setFont("SimSun", 12)
c.drawString(100, 750, "中文字符测试")
c.save()
```

### Markdown → PDF

```python
import markdown
from weasyprint import HTML

with open("readme.md") as f:
    md_text = f.read()
html = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
HTML(string=f"<html><body>{html}</body></html>").write_pdf("output.pdf")
```

## 合并 PDF

```python
import fitz

def merge_pdfs(input_files: list[str], output_path: str):
    merged = fitz.open()
    for file in input_files:
        doc = fitz.open(file)
        merged.insert_pdf(doc)
        doc.close()
    merged.save(output_path)
    merged.close()
```

## 拆分 PDF

```python
def split_pdf(input_path: str, output_dir: str):
    doc = fitz.open(input_path)
    for i, page in enumerate(doc):
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=i, to_page=i)
        new_doc.save(f"{output_dir}/page_{i+1}.pdf")
        new_doc.close()
    doc.close()
```

## 填写 PDF 表单

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("form.pdf")
writer = PdfWriter()

writer.append(reader)
writer.update_page_form_field_values(
    writer.pages[0],
    {"name": "张三", "phone": "13800138000", "address": "北京市朝阳区"}
)

with open("filled_form.pdf", "wb") as f:
    writer.write(f)
```

## 提取图片

```python
import fitz
import os

doc = fitz.open("document.pdf")
os.makedirs("images", exist_ok=True)

for page_num, page in enumerate(doc):
    images = page.get_images()
    for img_idx, img in enumerate(images):
        xref = img[0]
        pix = fitz.Pixmap(doc, xref)
        if pix.n < 5:  # GRAY 或 RGB
            pix.save(f"images/page{page_num+1}_img{img_idx+1}.png")
        else:  # CMYK → 转 RGB
            pix = fitz.Pixmap(fitz.csRGB, pix)
            pix.save(f"images/page{page_num+1}_img{img_idx+1}.png")
doc.close()
```

## 注意事项

1. **中文字体**：ReportLab 生成 PDF 时中文默认无法显示，必须注册 TTF 字体
2. **weasyprint 系统依赖**：macOS 不需要额外安装，Linux 需要 `libpango` 等系统库
3. **大文件处理**：对 100MB+ 的 PDF，`pymupdf` 比 `pypdf` 快 10 倍以上
4. **扫描件 PDF**：纯扫描件（无文字层）需要用 OCR（pytesseract + pdf2image）
5. **水印**：用 `pymupdf` 的 `page.insert_image()` 叠加半透明图片可加水印
