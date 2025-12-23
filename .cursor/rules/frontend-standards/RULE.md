---
description: "Frontend standards for React/TypeScript (imports, forms, state, API usage, strict null handling, shadcn/ui)."
alwaysApply: false
globs:
  - "frontend/**"
---

# Frontend Standards (React / TypeScript) — migrated from Copilot instructions

## 🧩 Conventions

- **Imports**: use `@/` alias for `src/` (e.g., `import { Button } from "@/components/ui/button"`).
- **Forms**: use `react-hook-form` with `zod` resolvers.
- **State**: use `Context` for global state (e.g., `AuthContext`).
- **API**: use axios instances from `@/services/api`.
- **TypeScript strict mode**: `strict: true` is enabled. Handle `null` / `undefined` explicitly.

## 🎨 UI components

- Use shadcn/ui components from `@/components/ui`.
- Add components with `npx shadcn@latest add [component]`.
- When choosing UI components/patterns, prefer the most up-to-date shadcn/ui options and aim for the cleanest, most polished UX.

## ✅ End-of-implementation checks (must match CI)

When you change anything under `frontend/`, **do not finish** until these pass locally (same steps as `.github/workflows/frontend.yml`):

- **Install deps (when `package-lock.json` changes or deps feel stale)**: `npm ci`
- **Lint**: `npm run lint`
- **Tests**: `npm run test`
- **Build**: `npm run build`

Also:

- **Write/update tests** when behavior changes:
  - Unit/integration tests with **Vitest** + **Testing Library** (see `frontend/src/test/`).
  - Cover happy path + at least one failure/edge case for new logic.


