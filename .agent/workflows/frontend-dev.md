---
description: Build or modify a React frontend feature. Use for new pages, components, forms, or API integrations. Automatically checks shadcn for components before building custom ones.
---

# Frontend Development Workflow

## Step 1 — Discover available components and existing patterns
// parallel

### Shadcn Scout
Task: Use the shadcn MCP tool to list available components relevant to this feature.
Find the best existing shadcn components to use so we don't build custom ones unnecessarily.
// capture: AVAILABLE_COMPONENTS

### Feature Reader
Task: Read the target feature directory (frontend/src/features/<feature>/).
Summarize existing api.ts, components, and types patterns to follow.
// capture: EXISTING_PATTERNS

## Step 2 — Plan
> Using $AVAILABLE_COMPONENTS and $EXISTING_PATTERNS, outline:
> - Which shadcn components to use
> - New components to create and their props
> - api.ts functions needed (typed axios calls)
> - Form schema (zod) if there's a form
> - State management approach (local useState vs Context)
> WAIT FOR APPROVAL before implementing.

## Step 3 — Implement
Role: React Frontend Specialist
Use the `shadcn-ui` and `react-best-practices` skills.

Follow strictly:
- @/ imports — no relative cross-feature imports
- API calls only in api.ts, never inline in components
- react-hook-form + zod for all forms
- TailwindCSS v4 + cn() — no inline styles
- TypeScript strict — handle null/undefined explicitly
- One component per file, named same as the file

## Step 4 — Lint and build
// turbo
cd frontend && npm run lint
// turbo
cd frontend && npm run build
// capture: BUILD_RESULT

> If lint errors or build fails, fix before proceeding.

## Step 5 — Ship (optional)
// if BUILD_RESULT is success and user wants to push
// run workflow: github-push
