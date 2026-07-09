---
name: ppt
description: PowerPoint 操作。用户需要创建、编辑、排版、导出 PPT 演示文稿时使用。
tools: [execute_python]
complete_tool: complete_task
---

# PowerPoint 操作指南

## 工具选择

优先使用 `python-pptx` 库（纯 Python，无需安装 Office）。

## 创建新演示文稿

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor

prs = Presentation()
prs.slide_width = Inches(13.333)   # 16:9 宽屏
prs.slide_height = Inches(7.5)
```

## 常用操作

### 添加空白幻灯片

```python
blank_layout = prs.slide_layouts[6]  # 空白布局
slide = prs.slides.add_slide(blank_layout)
```

### 添加文本框

```python
left, top, width, height = Inches(1), Inches(2), Inches(11), Inches(3)
textbox = slide.shapes.add_textbox(left, top, width, height)
tf = textbox.text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "标题文字"
p.font.size = Pt(44)
p.font.bold = True
p.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
```

### 添加表格

```python
shape = slide.shapes.add_table(rows=5, cols=3, left=Inches(1), top=Inches(2.5), width=Inches(11), height=Inches(3))
table = shape.table
for i, header in enumerate(["列1", "列2", "列3"]):
    table.cell(0, i).text = header
```

### 添加图片

```python
slide.shapes.add_picture("chart.png", Inches(1), Inches(3), Inches(11), Inches(3.5))
```

## 排版规范

1. **标题**: 44pt，深色 (#1a1a2e)，左对齐
2. **正文**: 18pt，中灰色 (#333333)，行距 1.5 倍
3. **留白**: 左右边距 ≥ 1 inch，上下边距 ≥ 0.8 inch
4. **配色**: 全 PPT 不超过 3 种主色
5. **单页要点**: 不超过 5 条，每条不超过 15 个字

## 保存

```python
prs.save("output.pptx")
print("PPT 已保存为 output.pptx")
```

## 注意事项

- 中文内容建议使用"微软雅黑"或"思源黑体"
- 生成后提醒用户手动检查排版
