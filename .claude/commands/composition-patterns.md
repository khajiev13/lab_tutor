React composition patterns that scale. Use when refactoring components with boolean prop proliferation, building flexible component libraries, or designing reusable APIs.

Read the full skill and rules:
- .github/skills/vercel-composition-patterns/SKILL.md
- .github/skills/vercel-composition-patterns/AGENTS.md (full compiled guide)
- Individual rules in .github/skills/vercel-composition-patterns/rules/

## Rule Categories

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Component Architecture | HIGH | `architecture-` |
| 2 | State Management | MEDIUM | `state-` |
| 3 | Implementation Patterns | MEDIUM | `patterns-` |
| 4 | React 19 APIs | MEDIUM | `react19-` |

## Key Rules
- `architecture-avoid-boolean-props` — Don't add boolean props to customize behavior; use composition
- `architecture-compound-components` — Structure complex components with shared context
- `state-decouple-implementation` — Provider is the only place that knows how state is managed
- `state-context-interface` — Define generic interface with state, actions, meta
- `patterns-explicit-variants` — Create explicit variant components instead of boolean modes
- `patterns-children-over-render-props` — Use children for composition
- `react19-no-forwardref` — Don't use `forwardRef`; use `use()` instead of `useContext()`

$ARGUMENTS
