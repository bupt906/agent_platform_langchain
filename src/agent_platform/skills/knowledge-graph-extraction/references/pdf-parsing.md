# PDF Parsing Strategies for KG Extraction

Phase 1 (Intake & parse) must produce clean plain text. Different PDF generators
produce PDFs that require different extraction strategies. Try them in order;
stop when you get usable text.

## Strategy order

1. **`read_file` (built-in)** — Works for most PDFs/DOCX. Hermes auto-extracts
   text from docx/pptx/ipynb via the file-reading tool. This is the first thing
   to try.

2. **`pdftotext` (poppler-utils)** — Fallback when `read_file` produces garbled
   binary content. Install if absent: `apt install poppler-utils`. Produces
   clean UTF-8 text for most PDFs. Run:
   ```bash
   pdftotext input.pdf output.txt
   ```
   This solves the WPS PDF problem where `read_file` dumps Type3 font glyph
   streams as raw binary instead of extracting text.

3. **`pymupdf` (fitz) or `pdfplumber` (Python)** — For PDFs where pdftotext
   also fails (scanned/image-only PDFs, complex tables). Install with pip in a
   venv. These libraries offer more control but are heavier dependencies.

## WPS PDF specific issues

PDFs created by WPS (金山WPS) often use **Type3 embedded fonts** where each
character glyph is stored as a separate image stream. The raw file is large
(10+ MB for a few hundred words) because the "text" is actually rendered glyphs.
`pdftotext` handles these correctly by using the ToUnicode CMap embedded in the
PDF; `read_file` on the raw binary does not.

**Signs you hit this:** `read_file` output is thousands of lines of binary
garbage, `%PDF-1.7` header followed by raw font streams with `/Subtype/Type3`,
and the file size is disproportionately large for the page count.

## When text is still incomplete

If `pdftotext` extracts only the first N pages and stops (e.g., 8 of 200 pages),
the remaining pages may be scanned images. In that case:
- Note the limitation in the extraction report
- Suggest the user provide the original Word/document source or run OCR
- Do NOT attempt OCR yourself unless the user explicitly asks
