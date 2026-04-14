# Bilingual Output Specification

Authoritative format specification for paragraph-by-paragraph English + Chinese comparison output across all eligible Skills.

## Quick Reference

| Output Format | Chinese Encoding | Paragraph Marker | File Suffix |
|---|---|---|---|
| LaTeX (.tex) | `%` comment lines | `% --- Paragraph N ---` | `_bilingual.tex` |
| Markdown (.md) | `> **[Chinese]**` blockquote | `<!-- Paragraph N -->` | `_bilingual.md` (or inline) |

## Format Variants

### LaTeX Comment Format (.tex output)

```latex
% --- Paragraph 1 ---
% 城市热岛效应（urban heat island effect）已成为城市规划和公共健康研究中日益重要的议题。
% 理解街道层面的语义特征如何塑造居民的安全感知，对于循证城市设计至关重要。
The urban heat island effect has become increasingly important in urban planning and public-health research.
Understanding how street-level semantics shape perceived safety is essential for evidence-based urban design.

% --- Paragraph 2 ---
% 然而，现有研究在解释街道层面语义特征与感知安全之间的关系方面仍存在局限。
However, existing studies remain limited in their ability to explain how street-level semantics relate to perceived safety.
```

### Markdown Blockquote Format (.md output)

```markdown
<!-- Paragraph 1 -->
**Problem:** The Introduction proposes a "multi-scale prediction framework," but Methods describes a single-scale gradient boosting model.

**Why this matters:** Reviewers will note the mismatch between the stated contribution and the actual implementation.

**Suggestion:** Update the Introduction to describe a single-scale model, or add a multi-scale component to Methods.

> **[Chinese]** 问题：引言提出"多尺度预测框架"（multi-scale prediction framework），但方法章节仅描述单尺度梯度提升模型（gradient boosting model）。为什么重要：审稿人会注意到声明贡献与实际实现之间的不一致。建议：修改引言或在方法中补充多尺度组件。
```

## When to Use Each Variant

Output format determines variant, not Skill identity. If a Skill produces `.tex` files, use LaTeX comment format. If a Skill produces `.md` files or conversation output, use Markdown blockquote format.

## Display Order

English first, Chinese after. English is the primary submission text; Chinese is an auxiliary comprehension aid.

## Paragraph Markers

- **LaTeX:** `% --- Paragraph N ---` (REQUIRED for all paragraph-level bilingual files)
- **Markdown:** `<!-- Paragraph N -->` (REQUIRED for paragraph-level bilingual files; OPTIONAL for structured-output Skills like reviewer-simulation and logic where document structure already provides navigation)

## File Naming Convention

- Bilingual files use `_bilingual` suffix: `intro_bilingual.tex`, `abstract_bilingual.md`
- Skills that embed bilingual inline (reviewer, logic -- per-concern blockquotes, not paragraph-level files) keep their existing naming (e.g., `_review.md`, `_logic.md`)

## Opt-Out Mechanism

- **Default:** Bilingual ON for all eligible Skills
- **Opt-out:** Case-insensitive phrase detection in user's trigger prompt
- **Keywords** (exact phrases, not substrings): `english only`, `no bilingual`, `only english`, `不要中文`
- **When detected:** Skip all Chinese output, produce English-only output
- **No AskUserQuestion needed** for toggle -- keyword detection is automatic

## Chinese Translation Quality Guidelines

- **Purpose:** Auxiliary comprehension aid, not standalone Chinese paper
- **Terminology:** Preserve English terms with Chinese in parentheses -- e.g., "urban heat island（城市热岛）"
- **Register:** Academic written Chinese (学术书面语) -- use "本研究提出了..." not "我们做了..."
- **Glossary:** If user provides a glossary file, use it for term mappings. Otherwise translate based on domain knowledge
- **Standardized label:** Always use `**[Chinese]**` (not `**[中文]**`) for Markdown blockquote labels

## Edge Cases

- **Mixed Chinese-English input:** Treat the entire paragraph as one unit; do not split by language
- **Very short paragraphs** (1-2 sentences): Still produce bilingual pair; do not merge with adjacent paragraphs

## Migration Checklist (Phase 17)

| Skill | Current State | Output Type | Changes Needed |
|---|---|---|---|
| translation | Full LaTeX bilingual | LaTeX file | Add `references/bilingual-output.md` to references; verify opt-out keywords |
| reviewer-simulation | Full Markdown bilingual (`**[Chinese]**`) | Markdown | Add reference; add paragraph markers; add opt-out keywords |
| logic | Full Markdown bilingual (`**[中文]**`) | Markdown | Add reference; change label to `**[Chinese]**`; add paragraph markers; add opt-out keywords |
| polish | No bilingual | LaTeX in-place | Add bilingual output variant; add reference; add opt-out keywords |
| de-ai | No bilingual | LaTeX in-place | Add bilingual output variant; add reference; add opt-out keywords |
| abstract | No bilingual | Conversation | Add Markdown blockquote bilingual; add reference; add opt-out keywords |
| experiment | No bilingual | Conversation/file | Add Markdown blockquote bilingual; add reference; add opt-out keywords |

---

*Specification: references/bilingual-output.md*
*Conventions: references/skill-conventions.md*
