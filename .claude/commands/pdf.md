PDF processing guide. Use when reading, extracting, merging, splitting, rotating, creating, filling forms, encrypting, or doing OCR on PDF files.

Read the full skill for detailed code examples:
- .github/skills/pdf/SKILL.md
- .github/skills/pdf/reference.md (advanced features, JS libraries, troubleshooting)
- .github/skills/pdf/forms.md (filling PDF forms)

## Quick Reference

| Task | Best Tool | Command/Code |
|------|-----------|--------------|
| Merge PDFs | pypdf | `writer.add_page(page)` |
| Split PDFs | pypdf | One page per file |
| Extract text | pdfplumber | `page.extract_text()` |
| Extract tables | pdfplumber | `page.extract_tables()` |
| Create PDFs | reportlab | Canvas or Platypus |
| Command line merge | qpdf | `qpdf --empty --pages ...` |
| OCR scanned PDFs | pytesseract | Convert to image first |
| Fill PDF forms | pdf-lib or pypdf | See forms.md |

## Key Notes
- Never use Unicode subscript/superscript characters in ReportLab — use `<sub>` and `<super>` tags
- For form filling, read .github/skills/pdf/forms.md first

$ARGUMENTS
