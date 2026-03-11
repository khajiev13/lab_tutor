# Plan: Agent-Centric UI for Curricular Alignment Architect

Restructure the course detail page from a flat stepper into an **Agent Hub** pattern — a course landing page showing agents as cards, each linking to a dedicated agent workspace. The Curricular Alignment Architect keeps its stepper workflow but gains an **agent identity** (avatar, name, description) and a **live activity feed**. This establishes a scalable pattern for Market Demand Analyst and future agents.

---

## Phase 1: Route restructure & Agent Hub page

1. **Create Agent Hub page** — New `AgentHubPage.tsx` in `frontend/src/features/courses/pages/`. Shows course header + a grid of agent cards. Each card: agent avatar/icon, name, description, status badge (Not Started / In Progress / Complete), and a progress indicator. Clicking navigates to `/courses/:id/architect`.

2. **Move current stepper to architect route** — Current teacher content from `TeacherCourseDetail.tsx` (stepper + steps) moves to a new `ArchitectAgentPage.tsx` at route `/courses/:id/architect`. Wraps the existing `CourseDetailProvider`. *(depends on step 1)*

3. **Update routes in `App.tsx`** — New routes:
   - `/courses/:id` → `AgentHubPage` (replaces current stepper landing)
   - `/courses/:id/architect` → `ArchitectAgentPage` (relocated workflow)
   - Existing `/courses/:id/graph` and `/courses/:id/reviews/:reviewId` unchanged
   - Student view stays on the hub page

## Phase 2: Agent identity & activity feed

4. **Create `AgentPageHeader`** — Reusable header for every agent page: avatar (icon in a colored circle), agent name, one-line description, overall status badge. In `frontend/src/features/agents/components/`. *(parallel with step 5)*

5. **Create `AgentActivityFeed`** — A `ScrollArea`-based log panel showing timestamped events ("Discovering books…", "Scored 3/10 books", "Downloading PDFs…"). Uses shadcn `Spinner` for in-progress operations and `Empty` for the zero-activity state. Pulls from existing polling data in `CourseDetailContext`. *(parallel with step 4)*

6. **Integrate into `ArchitectAgentPage`** — Agent header above the stepper, separated by `Separator`. Content area uses shadcn `Tabs` with two tabs: **Workflow** (stepper) and **Activity** (feed). This keeps the layout clean on mobile and gives each concern dedicated screen space. *(depends on 4, 5)*

## Phase 3: Agent card & hub wiring

7. **Create `AgentCard` component** — Reusable hub card. Uses shadcn `Card` + `Avatar` + `Badge` + `Progress`. Wrap status badges in `Tooltip` to explain what each status means (e.g., hovering "In Progress" → "The architect is currently discovering and scoring books…"). Wrap card in `HoverCard` to show a quick preview (last activity, completion %, quick stats) on hover without requiring a click. Disabled/coming-soon agents use the `Empty` component inside the card body (icon + "Coming Soon" + brief description) instead of just a badge. *(parallel with 4-6)*

8. **Define agent registry** — Simple config array in `frontend/src/features/agents/config.ts`:
   - `{ id: "architect", name: "Curricular Alignment Architect", icon: BookOpen, route: "architect", enabled: true }`
   - `{ id: "market-analyst", name: "Market Demand Analyst", icon: TrendingUp, route: "market-analyst", enabled: false }`
   - Adding a new agent = add to config + create page + wire route. *(parallel with 7)*

9. **Wire `AgentHubPage` to render cards** from registry, fetch per-agent status, render. Use `Skeleton` placeholders for each card while status is loading. Disabled agents show `Empty` state inside the card. *(depends on 7, 8)*

## Phase 4: Navigation polish

10. **Breadcrumb navigation** — On agent pages: `Courses > Course Name > Agent Name`. Use the shadcn `Breadcrumb` component (`<Breadcrumb> <BreadcrumbList> <BreadcrumbItem>` composition) — provides proper `<nav aria-label="breadcrumb">` semantics, separator customization, and responsive truncation out of the box. Install with `npx shadcn@latest add breadcrumb`. *(depends on 3)*

11. **Sidebar** — No structural changes. `My Courses` → `/courses` → click course → hub → click agent. Linear flow preserved.

---

## Relevant files

### Create
- `frontend/src/features/agents/components/AgentCard.tsx`
- `frontend/src/features/agents/components/AgentPageHeader.tsx`
- `frontend/src/features/agents/components/AgentActivityFeed.tsx`
- `frontend/src/features/agents/components/AgentHubGrid.tsx` — responsive grid layout with `Skeleton` loading and `Empty` zero-agent state
- `frontend/src/features/agents/config.ts`
- `frontend/src/features/courses/pages/AgentHubPage.tsx`
- `frontend/src/features/courses/pages/ArchitectAgentPage.tsx`

### Modify
- `frontend/src/App.tsx` — Add architect route, change course detail to hub
- `frontend/src/features/courses/pages/TeacherCourseDetail.tsx` — Extract teacher content into ArchitectAgentPage
- `frontend/src/features/courses/components/CourseStepperHeader.tsx` — Minor cleanup

### Reference (not modified)
- `frontend/src/components/ui/stepper.tsx`, `frontend/src/features/courses/context/CourseDetailContext.tsx`, `frontend/src/features/normalization/components/AgentVisualizer.tsx` — Patterns to reuse

### Shadcn components already installed
`Card`, `Avatar`, `Badge`, `Progress`, `ScrollArea`, `Collapsible`, `Skeleton`, `Tooltip`, `HoverCard`, `Tabs`, `Separator`

### Shadcn components to install
| Component | Why | Command |
|-----------|-----|---------|
| `breadcrumb` | Accessible breadcrumb nav (step 10) | `npx shadcn@latest add breadcrumb` |
| `empty` | Empty/coming-soon states for agents & feed | `npx shadcn@latest add empty` |
| `spinner` | Loading indicators in activity feed | `npx shadcn@latest add spinner` |

---

## Verification

1. Navigate `/courses/:id` → see Agent Hub with architect card
2. Click architect card → land on `/courses/:id/architect` with full stepper workflow
3. All 5 stepper steps work identically on the new route
4. Student view: `/courses/:id` still shows enrollment card
5. Graph page (`/courses/:id/graph`) and review pages still reachable
6. Activity feed reflects real-time status from existing polling
7. Market Demand Analyst card shows "Coming Soon", not clickable
8. Mobile responsive: cards stack, tabs switch between workflow and activity

---

## Decisions

- **No chat interface yet** — Workflow + activity log model per your selection
- **Teacher ↔ Agent only** — No inter-agent communication
- **Hub is the new course landing** — One extra click to reach the stepper, but establishes the multi-agent pattern
- **No new backend endpoints** — Activity feed derives from existing `CourseDetailContext` polling data
- **Agent registry is frontend-only** — Simple config array, no backend agents table until agents become dynamic

## Further Considerations

1. **Agent status API**: Currently we derive architect status from existing data. When Market Demand Analyst arrives, consider a unified `/courses/:id/agents/status` endpoint. **Recommendation**: Defer.

2. **Activity feed granularity**: Start coarse ("Scoring books…"), add fine-grained events later as SSE streams already exist for some operations.

3. **Future chat layer**: The `AgentActivityFeed` component can evolve into a bidirectional chat panel per-agent when conversational interaction is needed.
