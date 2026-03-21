Implementation plan for the Agent-Centric UI restructure.

Read the full plan: .github/prompts/plan-agentCentricUi.prompt.md

## Summary
Restructure the course detail page from a flat stepper into an Agent Hub pattern — a course landing page showing agents as cards, each linking to a dedicated agent workspace.

## Phases
1. Route restructure & Agent Hub page
   - AgentHubPage.tsx — grid of agent cards
   - ArchitectAgentPage.tsx — relocated stepper workflow at /courses/:id/architect
   - Update routes in App.tsx

2. Agent identity & activity feed
   - AgentPageHeader — avatar, name, description, status badge
   - AgentActivityFeed — ScrollArea log panel with timestamps
   - Integrate into ArchitectAgentPage with Tabs (Workflow / Activity)

3. Agent card & hub wiring
   - AgentCard component — Card + Avatar + Badge + Progress + HoverCard
   - Agent registry config array
   - Wire AgentHubPage to render from registry

4. Navigation polish
   - Breadcrumb navigation on agent pages

## Key Files to Create
- frontend/src/features/agents/components/ (AgentCard, AgentPageHeader, AgentActivityFeed, AgentHubGrid)
- frontend/src/features/agents/config.ts
- frontend/src/features/courses/pages/AgentHubPage.tsx
- frontend/src/features/courses/pages/ArchitectAgentPage.tsx

$ARGUMENTS
