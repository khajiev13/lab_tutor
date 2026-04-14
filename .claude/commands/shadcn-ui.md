shadcn/ui component patterns for this project. Use when adding UI components, customizing styles, composing primitives, or integrating forms with react-hook-form.

Read the full skill for detailed patterns and examples:
- .github/skills/shadcn-ui/SKILL.md
- .github/skills/shadcn-ui/references/examples.md
- .github/skills/shadcn-ui/references/recipes.md
- .github/skills/shadcn-ui/references/patterns.md

Also use the shadcn MCP server tool to check for the most up-to-date components.

## Core Principles
1. **Copy, don't import** — customize in `src/components/ui/`
2. **Compose, don't prop** — build from primitives
3. **className over props** — extend with Tailwind
4. **Accessibility first** — labels on icon buttons, FormControl wrappers
5. **Forms with react-hook-form** — use Form components with zod resolvers
6. **Mobile-first** — 44px minimum touch targets (WCAG 2.1 AAA)

## This Project
- Install: `npx shadcn@latest add [component]`
- Import: `import { Button } from "@/components/ui/button"`
- Styling: TailwindCSS v4 with `cn()` utility
- Toasts: Sonner (`toast.success(...)`)

$ARGUMENTS
