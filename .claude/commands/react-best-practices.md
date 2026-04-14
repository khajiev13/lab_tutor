React and Next.js performance optimization guidelines from Vercel Engineering. Use when writing, reviewing, or refactoring React code for optimal performance.

Read the full skill and individual rule files for detailed examples:
- .github/skills/vercel-react-best-practices/SKILL.md
- .github/skills/vercel-react-best-practices/AGENTS.md (full compiled guide)
- Individual rules in .github/skills/vercel-react-best-practices/rules/

## Rule Categories by Priority

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Eliminating Waterfalls | CRITICAL | `async-` |
| 2 | Bundle Size Optimization | CRITICAL | `bundle-` |
| 3 | Server-Side Performance | HIGH | `server-` |
| 4 | Client-Side Data Fetching | MEDIUM-HIGH | `client-` |
| 5 | Re-render Optimization | MEDIUM | `rerender-` |
| 6 | Rendering Performance | MEDIUM | `rendering-` |
| 7 | JavaScript Performance | LOW-MEDIUM | `js-` |
| 8 | Advanced Patterns | LOW | `advanced-` |

## Top Rules
- `async-parallel` — Use Promise.all() for independent operations
- `bundle-barrel-imports` — Import directly, avoid barrel files
- `bundle-dynamic-imports` — Use next/dynamic for heavy components
- `rerender-memo` — Extract expensive work into memoized components
- `rerender-derived-state-no-effect` — Derive state during render, not effects
- `rendering-conditional-render` — Use ternary, not && for conditionals

Read individual rule files in `rules/` for code examples.

$ARGUMENTS
