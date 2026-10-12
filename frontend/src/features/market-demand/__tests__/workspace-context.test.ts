import {describe, expect, it} from "vitest";
import {buildOccupationReferenceContext, buildRunReviewContext, copyWorkspaceContext, removeContextFocus, validateWorkspaceContext, isWorkspaceMessageValid} from "@/features/market-demand/workspace-context";
import {workspaceCandidateId, workspaceEvidenceFixture, workspaceEvidenceId, workspaceReviewFixture, workspaceRunId, workspaceSoc, workspaceOtherSoc, workspaceViewFixture} from "@/features/market-demand/__tests__/review-fixtures";
import type {RunReviewContext, WorkspaceContext, WorkspaceView} from "@/features/market-demand/types";

const input = () => ({review: workspaceReviewFixture(), view: workspaceViewFixture(), dirty: false, intent: "explain" as const});
const expected: RunReviewContext = {kind: "run_review", version: 1, intent: "explain", run_id: workspaceRunId,
  expected_candidate_revision: 1, expected_selection_revision: 2, view: "overview", focused_candidate_id: null,
  candidate_ids: [], filters: {category_ids: [], search: "", scope: "all"}, occupation_codes: [workspaceSoc, "15-1253.00"],
  metric: "IM", descriptor_choices: [], insight_kind: null, has_unsaved_changes: false};

describe("context builders", () => {
  it("sends only identities and filters with exact server field names", () => {
    const args = input();
    args.view.focusedCandidateId = workspaceCandidateId;
    expect(buildRunReviewContext(args)).toEqual({ok: true, context: {...expected, focused_candidate_id: workspaceCandidateId}});
    expect(buildRunReviewContext({...args, candidateIds: [workspaceCandidateId], insightKind: "common_sample"})).toEqual({ok: true,
      context: {...expected, focused_candidate_id: workspaceCandidateId, candidate_ids: [workspaceCandidateId], insight_kind: "common_sample"}});
  });
  it("permits dirty explanation with notice but requires save for selected scope or proposal", () => {
    const args = input();
    expect(buildRunReviewContext({...args, dirty: true})).toEqual({ok: true, context: {...expected, has_unsaved_changes: true}});
    expect(buildRunReviewContext({...args, dirty: true, view: {...args.view, filters: {...args.view.filters, scope: "selected"}}})).toEqual({ok: false, reason: "save_required"});
    expect(buildRunReviewContext({...args, dirty: true, intent: "propose_selection"})).toEqual({ok: false, reason: "save_required"});
    expect(buildRunReviewContext({...args, intent: "propose_selection"})).toEqual({ok: true, context: {...expected, intent: "propose_selection"}});
  });
  it("rejects no run; reference-only builder cannot propose a selection", () => {
    const args = input();
    expect(buildRunReviewContext({...args, review: {...args.review, run_id: null}})).toEqual({ok: false, reason: "invalid_context"});
    expect(buildOccupationReferenceContext({release: "30.0", occupationCodes: [workspaceSoc], elementIds: ["2.B.3.m"], metric: "LV"})).toEqual({ok: true,
      context: {kind: "occupation_reference", version: 1, intent: "explain", release: "30.0", occupation_codes: [workspaceSoc], element_ids: ["2.B.3.m"], metric: "LV"}});
  });
  it("removes run focus, compared candidates, choices and pattern without changing intent or scopes", () => {
    const context = {...expected, focused_candidate_id: workspaceCandidateId, candidate_ids: [workspaceCandidateId],
      descriptor_choices: [{candidate_id: workspaceCandidateId, evidence_id: workspaceEvidenceId}], insight_kind: "common_sample" as const};
    const before = JSON.stringify(context);
    expect(removeContextFocus(context)).toEqual(expected);
    expect(removeContextFocus({...context, intent: "propose_selection"}).intent).toBe("propose_selection");
    expect(JSON.stringify(context)).toBe(before);
    const reference = {kind: "occupation_reference", version: 1, intent: "explain", release: "30.0", occupation_codes: [workspaceSoc], element_ids: ["a"], metric: "IM"} as const;
    expect(removeContextFocus({...reference, occupation_codes: [...reference.occupation_codes], element_ids: [...reference.element_ids]})).toEqual({...reference, element_ids: []});
  });
  it("returns detached contexts so Send can freeze the copy before future edits", () => {
    const args = input();
    const result = buildRunReviewContext(args);
    if (!result.ok) throw new Error("Expected valid context");
    const copy = copyWorkspaceContext(result.context);
    args.view.filters.category_ids.push("tools");
    args.view.occupationCodes.pop();
    result.context.filters.search = "changed";
    result.context.descriptor_choices.push({candidate_id: workspaceCandidateId, evidence_id: workspaceEvidenceId});
    expect(copy).toEqual(expected);
    expect(result.context.filters.category_ids).toEqual([]);
  });
  it.each(["overview", "data", "demand_importance", "occupations"] satisfies WorkspaceView[])("rejects inconsistent explicit descriptors across occupations in %s", view => {
    const args = input();
    const otherId = "00000000-0000-0000-0000-000000000012";
    args.review.candidates[0].onet_associations = [workspaceEvidenceFixture(), workspaceEvidenceFixture({id: otherId, soc_code: workspaceOtherSoc, element_id: "2.B.3.k"})];
    args.view.view = view;
    args.view.descriptorChoices = [{candidate_id: workspaceCandidateId, evidence_id: workspaceEvidenceId}, {candidate_id: workspaceCandidateId, evidence_id: otherId}];
    expect(buildRunReviewContext(args)).toEqual({ok: false, reason: "invalid_context"});
  });
  it.each(["overview", "data", "demand_importance", "occupations"] satisfies WorkspaceView[])("accepts consistent descriptors with distinct role evidence IDs in %s", view => {
    const args = input();
    const otherId = "00000000-0000-0000-0000-000000000012";
    args.review.candidates[0].onet_associations = [workspaceEvidenceFixture(), workspaceEvidenceFixture({id: otherId, soc_code: workspaceOtherSoc})];
    args.view.view = view;
    args.view.descriptorChoices = [{candidate_id: workspaceCandidateId, evidence_id: workspaceEvidenceId}, {candidate_id: workspaceCandidateId, evidence_id: otherId}];
    const result = buildRunReviewContext(args);
    expect(result).toEqual({ok: true, context: {...expected, view, descriptor_choices: args.view.descriptorChoices}});
  });
  it.each(["IM", "LV"] as const)("rejects %s contexts without occupations in the builder", metric => {
    const args = input();
    args.view.metric = metric;
    args.view.occupationCodes = [];
    expect(buildRunReviewContext(args)).toEqual({ok: false, reason: "invalid_context"});
  });
  it.each(["IM", "LV"] as const)("rejects %s contexts without occupations in the strict validator", metric => {
    expect(validateWorkspaceContext({...expected, metric, occupation_codes: []})).toBe(false);
  });
  it("accepts frequency contexts with no occupations in the builder and strict validator", () => {
    const args = input();
    args.view.metric = "frequency";
    args.view.occupationCodes = [];
    expect(buildRunReviewContext(args)).toEqual({ok: true, context: {...expected, metric: "frequency", occupation_codes: []}});
    expect(validateWorkspaceContext({...expected, metric: "frequency", occupation_codes: []})).toBe(true);
  });
  it("validates confirmed occupations, member IDs, categories and eligible descriptor choices", () => {
    const args = input();
    args.review.candidates[0].onet_associations = [workspaceEvidenceFixture()];
    args.view.descriptorChoices = [{candidate_id: workspaceCandidateId, evidence_id: workspaceEvidenceId}];
    expect(buildRunReviewContext(args).ok).toBe(true);
    const invalid = [
      {...args, candidateIds: ["00000000-0000-0000-0000-000000000088"]},
      {...args, view: {...args.view, focusedCandidateId: "unknown"}},
      {...args, view: {...args.view, occupationCodes: ["99-9999.00"]}},
      {...args, view: {...args.view, filters: {...args.view.filters, category_ids: ["unknown"]}}},
      {...args, view: {...args.view, descriptorChoices: [{candidate_id: workspaceCandidateId, evidence_id: "00000000-0000-0000-0000-000000000088"}]}},
      {...args, view: {...args.view, descriptorChoices: [...args.view.descriptorChoices, ...args.view.descriptorChoices]}},
    ];
    for (const invalidInput of invalid) expect(buildRunReviewContext(invalidInput)).toEqual({ok: false, reason: "invalid_context"});
  });
});

describe("wire bounds match backend schemas", () => {
  it("enforces the message character bound without counting UTF-16 surrogate halves", () => {
    expect(isWorkspaceMessageValid("😀".repeat(8000))).toBe(true);
    expect(isWorkspaceMessageValid("😀".repeat(8001))).toBe(false);
    expect(isWorkspaceMessageValid(123)).toBe(false);
  });
  it.each([
    {candidate_ids: Array(21).fill(workspaceCandidateId)}, {occupation_codes: Array(6).fill(workspaceSoc)},
    {descriptor_choices: Array(21).fill({candidate_id: workspaceCandidateId, evidence_id: workspaceEvidenceId})},
    {filters: {...expected.filters, category_ids: Array(11).fill("tools")}}, {filters: {...expected.filters, search: "x".repeat(121)}},
    {candidate_ids: [workspaceCandidateId, workspaceCandidateId]}, {occupation_codes: [workspaceSoc, workspaceSoc]},
    {expected_candidate_revision: -1}, {expected_selection_revision: 1.5}, {run_id: "invalid"}, {metric: "bad"},
    {view: "bad"}, {view: ["overview"]}, {metric: ["IM"]}, {intent: ["explain"]}, {intent: "bad"}, {version: true}, {has_unsaved_changes: "false"}, {facts: []},
    {filters: {...expected.filters, country: "UZ"}}, {descriptor_choices: [{candidate_id: workspaceCandidateId, evidence_id: workspaceEvidenceId, value: 4}]},
  ])("rejects invalid run context %j", patch => {
    expect(validateWorkspaceContext({...expected, ...patch})).toBe(false);
  });
  it("counts Unicode characters for search and UTF-8 bytes for the context budget", () => {
    expect(validateWorkspaceContext({...expected, filters: {...expected.filters, search: "😀".repeat(120)}})).toBe(true);
    expect(validateWorkspaceContext({...expected, filters: {...expected.filters, search: "😀".repeat(121)}})).toBe(false);
    expect(validateWorkspaceContext({...expected, filters: {...expected.filters, category_ids: ["界".repeat(6000)]}})).toBe(false);
    expect(validateWorkspaceContext({...expected, filters: {...expected.filters, category_ids: ["界".repeat(5000)]}})).toBe(true);
  });
  it("rejects invalid reference fields, duplicates and bounds without truncation", () => {
    const reference: WorkspaceContext = {kind: "occupation_reference", version: 1, intent: "explain", release: "30.0", occupation_codes: [workspaceSoc], element_ids: [], metric: "IM"};
    for (const patch of [{release: "latest"}, {release: "1".repeat(20) + ".0"}, {occupation_codes: []}, {occupation_codes: ["bad"]},
      {element_ids: Array(21).fill("x")}, {element_ids: ["a", "a"]}, {element_ids: [""]}, {element_ids: ["x".repeat(31)]},
      {metric: "frequency"}, {intent: "propose_selection"}, {candidate_ids: []}]) {
      expect(validateWorkspaceContext({...reference, ...patch})).toBe(false);
    }
  });
});
