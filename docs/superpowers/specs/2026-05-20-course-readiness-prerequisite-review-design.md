# Course Readiness and Prerequisite Review Design

Status: ready for user review
Date: 2026-05-20

## Summary

Add a teacher-facing Course Readiness Road that guides a draft course toward
student availability. A course becomes discoverable and enrollable by students
only after required readiness gates are complete.

The first required gates are:

1. Book skill bank completed through the Curricular Alignment Architect.
2. Market skill bank completed through the Market Demand Analyst.
3. Prerequisite graph reviewed and approved by the teacher.
4. Course published by the teacher.

Prerequisites become a required teacher-in-the-loop gate. The AI can generate or
regenerate prerequisite edges, but the teacher must review the graph before the
course can be published.

## Goals

- Make the teacher course page answer: what should I click next?
- Keep agent icons and agent workspaces as the primary teacher actions.
- Add a separate Prerequisite Review launcher because the graph combines book
  and market skill outputs.
- Make publication meaningful: students discover and enroll only in published
  courses.
- Let teachers approve, remove, and add prerequisite edges before publishing.
- Show isolated skills as reviewed standalone skills, not automatic defects.
- Invalidate prerequisite approval when book or market skills change.

## Non-Goals

- Do not build freeform drag-and-drop graph editing in the MVP.
- Do not require every skill to have a prerequisite or dependent edge.
- Do not create a full per-edge audit trail in the MVP.
- Do not replace existing book-selection or market-demand workspaces.

## Current Context

Students currently list all courses through `GET /courses`, and joining only
checks that the course exists. The design changes this so student discovery and
joining are limited to published courses.

The existing prerequisite pipeline is automatic:

- `POST /book-selection/courses/{course_id}/skill-prerequisites/build` starts
  the build.
- The LangGraph flow embeds skills, deduplicates, clusters, asks the LLM for
  prerequisite edges, enforces a DAG, and persists `PREREQUISITE` relationships
  in Neo4j.
- Book skill mapping and market skill insertion can auto-schedule prerequisite
  rebuilds.

The existing project already has teacher governance elsewhere:

- Book selection pauses for teacher review.
- Market demand asks teachers to confirm country, job groups, and skill
  selection before insertion.

This design adds the missing teacher governance surface for prerequisites.

## Teacher UX

The teacher course page gets a Course Readiness Road near the top of the page.
The road is a guide layer, not a replacement for agent pages.

The page includes:

- A readiness badge: draft, published, or publishing paused.
- A next-action banner with one primary button.
- Separate clickable launchers for:
  - Curricular Alignment Architect.
  - Market Demand Analyst.
  - Prerequisite Review.
- A compact readiness track showing gate status.
- A publish button that stays disabled until all required gates pass.

Example next actions:

- If book skill bank is incomplete: continue in Curricular Alignment Architect.
- If market skill bank is incomplete: continue in Market Demand Analyst.
- If prerequisites need review: open Prerequisite Review.
- If everything is ready: publish course.
- If a published course becomes stale: review regenerated prerequisites before
  publishing is considered active again.

## Prerequisite Review UX

The review page uses an edge worklist plus a live graph preview.

Main zones:

- Edge worklist: AI-generated edges with prerequisite skill, dependent skill,
  confidence, and reasoning.
- Live DAG preview: visual graph updated as edges are added or removed.
- Isolated skills: skills with no prerequisite or dependent edges.

Teacher actions:

- Keep AI-generated edges.
- Remove edges that do not make sense.
- Add missing edges through searchable skill pickers.
- Regenerate AI suggestions.
- Approve the graph when valid.

Approval requirements:

- Every edge references existing skills in the course skill bank.
- The graph is acyclic.
- The teacher has viewed isolated skills.
- The graph is not currently rebuilding.

If a teacher adds an edge that creates a cycle, approval is blocked and the UI
shows the cycle path.

## State Model

Add a course publication status:

- `draft`: default state; visible to teacher, not discoverable by students.
- `published`: discoverable and enrollable by students.

Add prerequisite review status:

- `not_started`: no generated prerequisite graph exists yet.
- `needs_review`: AI generated or regenerated prerequisites and teacher review
  is required.
- `approved`: teacher approved the current prerequisite graph.
- `stale`: skill-bank changes occurred after teacher approval.

The publication gate treats both `needs_review` and `stale` as blocking states.
A course is available to new students only when `publication_status = published`
and prerequisite review status is `approved`. If a published course becomes
stale, the teacher UI should show "publishing paused" until review is refreshed.

## Readiness Gate Definitions

Book skill bank is complete when the teacher-selected book workflow has produced
mapped book skills for the course.

Market skill bank is complete when the Market Demand Analyst has finished its
teacher-approved insertion path. If the teacher explicitly confirms that no
market skills should be inserted, that confirmation counts as a completed market
gate.

Prerequisite review is complete when the teacher approves the current
prerequisite review draft and the backend has written the approved graph to
Neo4j.

## Review Metadata

Store the final approved graph in Neo4j as `PREREQUISITE` relationships. The
AI-generated graph and teacher edits are treated as a review draft until the
teacher approves them.

Store one simple SQL review row per course:

- `course_id`
- `review_status`
- `draft_edges`
- `approved_by`
- `approved_at`
- `edge_count`
- `generated_edge_count`
- `added_edge_count`
- `removed_edge_count`
- `isolated_skill_count`
- `last_generated_at`
- `last_invalidated_at`

The MVP does not store a full per-edge audit trail.

## Backend Design

Add a readiness/publication layer under `backend/app/modules/courses/`.

Endpoints:

- `GET /courses/{course_id}/readiness`
  - Teacher-only.
  - Returns gate status, blockers, next action, publication status, and
    prerequisite review summary.
- `POST /courses/{course_id}/publish`
  - Teacher-only.
  - Publishes only when every required gate passes.
- `POST /courses/{course_id}/unpublish`
  - Teacher-only.
  - Reverts a course to draft when the teacher intentionally removes it from
    student discovery.

Update student-facing course behavior:

- `GET /courses` returns only published courses for students.
- `POST /courses/{course_id}/join` rejects courses whose effective availability
  is blocked by draft publication status or stale prerequisite review.
- Teachers continue seeing their own draft and published courses.

Add prerequisite review service and repository code under
`backend/app/modules/curricularalignmentarchitect/skill_prerequisites/`, then
register routes through the existing skill prerequisite API route file:

- `GET /book-selection/courses/{course_id}/skill-prerequisites/review`
  - Returns skills, draft edges, isolated skills, review status, and metadata.
- `PUT /book-selection/courses/{course_id}/skill-prerequisites/review`
  - Saves the teacher-edited edge draft.
- `POST /book-selection/courses/{course_id}/skill-prerequisites/approve`
  - Validates and persists the final graph, then marks review approved.
- `POST /book-selection/courses/{course_id}/skill-prerequisites/regenerate`
  - Runs the existing prerequisite pipeline into the review draft and marks the
    review as needing review.

Backend validation:

- Check teacher owns the course.
- Check all edge endpoints are valid course skills.
- Check no self-edges exist.
- Check no duplicate edges exist.
- Check the graph remains acyclic.
- Write Neo4j with `MERGE` and batched `UNWIND`.

Pipeline persistence change:

- Generated prerequisite candidates should be saved as the course review draft.
- The live Neo4j `PREREQUISITE` graph should be replaced only by the approve
  endpoint after validation.
- Existing enrolled students can continue using the last approved graph while a
  newer draft is waiting for teacher review.

## Invalidation Rules

Prerequisite approval is invalidated when skill-bank inputs change.

Invalidating events:

- Book skill mapping completes and schedules prerequisite rebuild.
- Market skill insertion updates `insertion_results`.
- Manual prerequisite regeneration is requested.

If the course is published and prerequisites become stale, the course should no
longer be available for new student discovery or enrollment until the teacher
reviews the new graph. Existing enrollments are not removed, and the last
approved graph remains live until a new graph is approved.

## Frontend Design

Add a readiness API wrapper under the course feature API layer.

Add teacher course page components:

- `CourseReadinessRoad`
- `NextActionBanner`
- `ReadinessGateTrack`
- `ReadinessAgentLauncher`
- `PublishCourseButton`

Add a prerequisite review feature area:

- `PrerequisiteReviewPage`
- `PrerequisiteEdgeWorklist`
- `PrerequisiteGraphPreview`
- `IsolatedSkillsPanel`
- `AddPrerequisiteEdgeDialog`
- `PrerequisiteReviewSummary`

Routing:

- Add a teacher route such as `/courses/:id/prerequisites`.
- The readiness road links the prerequisite launcher to that route.

The review page can reuse existing graph layout helpers where practical, but it
should not depend on student learning path UI internals if that creates tight
coupling.

## Testing

Backend tests:

- Student course listing returns only published courses.
- Student join rejects courses whose effective availability is blocked.
- Teacher can publish only when all gates pass.
- Publish returns blockers when gates are incomplete.
- Prerequisite approval fails for cycles.
- Prerequisite approval fails for unknown skills.
- Regeneration invalidates previous approval.
- Existing enrolled students are not removed when a course becomes stale.

Frontend tests:

- Course readiness road shows the correct next action.
- Publish button is disabled with visible blockers.
- Prerequisite launcher appears separately from existing agents.
- Edge worklist supports remove and add flows.
- Isolated skills are visible but not blocking by default.
- Cycle warning blocks approval.
- Published course cards are visible to students; draft courses are hidden.

## Rollout Notes

The implementation should happen in small slices:

1. Add publication state and student visibility gates.
2. Add readiness endpoint and teacher readiness road.
3. Add prerequisite review metadata and invalidation.
4. Add prerequisite review page with edge worklist and graph preview.
5. Add publish flow and final verification.

Database migrations are required for course publication state and prerequisite
review metadata.

## Approved Product Decisions

- Publication is a required gate.
- Public means discoverable and enrollable by any student in the app.
- Use a Course Readiness Road with deep links, not a separate final-only wizard.
- Keep agent icons as primary launchers.
- Add Prerequisite Review as its own separate launcher.
- Use edge worklist plus live graph preview for MVP.
- Show isolated skills but do not force them to be connected.
- Store simple review metadata, not a full audit trail.
- Regeneration after book or market skill changes invalidates prerequisite
  approval.
