---
name: ppt
description: PowerPoint 操作指南 —— 创建、编辑、排版、导出幻灯片
keywords:
  - PPT
  - PowerPoint
  - 幻灯片
  - 演示文稿
  - pptx
  - 排版
  - keynote
---

# PowerPoint 操作指南

## 工具选择

优先使用 `python-pptx` 库（纯 Python，无需安装 Office）。

```bash
pip install python-pptx
```

## 创建新演示文稿

```python
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
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
from pptx.util import Inches, Pt

left = Inches(1)
top = Inches(2)
width = Inches(11)
height = Inches(3)
textbox = slide.shapes.add_textbox(left, top, width, height)
tf = textbox.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "标题文字"
p.font.size = Pt(44)
p.font.bold = True
p.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
```

### 添加图片

```python
img = slide.shapes.add_picture("chart.png", Inches(1), Inches(3), Inches(11), Inches(3.5))
```

### 添加表格

```python
table = slide.shapes.add_table(rows=5, cols=3, left=Inches(1), top=Inches(2.5), width=Inches(11), height=Inches(3)).table

# 写表头
for i, header in enumerate(["列1", "列2", "列3"]):
    cell = table.cell(0, i)
    cell.text = header
```

### 设置背景色

```python
background = slide.background
fill = background.fill
fill.solid()
fill.fore_color.rgb = RGBColor(0xf5, 0xf5, 0xf5)
```

## 排版规范

1. **标题**：44pt，深色（#1a1a2e），左对齐
2. **正文**：18pt，中灰色（#333333），行距 1.5 倍
3. **留白**：左右边距 ≥ 1 inch，上下边距 ≥ 0.8 inch
4. **配色**：全 PPT 不超过 3 种主色，推荐一套深蓝系：`#1a1a2e` `#16213e` `#0f3460` `#e94560`
5. **单页要点**：不超过 5 条，每条不超过 15 个字

## 保存

```python
prs.save("output.pptx")
```

## 注意事项

- 中文内容需要确认字体在目标机器上存在，建议使用"微软雅黑"或"思源黑体"
- 如果模板文件来自企业模板 `.potx`：`prs = Presentation("template.potx")`
- 生成后建议提醒用户手动检查排版（python-pptx 的自动换行计算不完全准确）
