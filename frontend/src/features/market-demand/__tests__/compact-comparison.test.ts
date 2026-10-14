import {describe, expect, it} from "vitest";
import {buildCompactComparison} from "@/features/market-demand/compact-comparison";
import {reviewFixture, workspaceEvidenceFixture, workspaceReviewFixture, workspaceSoc} from "@/features/market-demand/__tests__/review-fixtures";
import {resolveOnetRating} from "@/features/market-demand/workspace-data";
import type {OnetAssociation} from "@/features/market-demand/types";

function association(id: string, element: string, label: string, value: number, relation: OnetAssociation["relation"] = "equivalent") {
  const item = workspaceEvidenceFixture({id, element_id: element, label});
  item.relation = relation;
  item.evidence.ratings.IM!.value = value;
  return item;
}
function fixture() {
  const review = workspaceReviewFixture();
  review.analysis_metadata!.occupations[0].title = "Database Architects";
  const base = reviewFixture().candidates[0];
  review.candidates = [
    {...base, candidate_id: "sql", display_name: "SQL", onet_associations: [association("programming", "programming", "Programming", 3.38, "related")]},
    {...base, candidate_id: "etl", display_name: "ETL", onet_associations: []},
    {...base, candidate_id: "design", display_name: "Design", onet_associations: [association("design", "design", "Design", 4.2)]},
  ];
  return review;
}

describe("compact evidence comparison", () => {
  it("shows related descriptor context without turning it into the candidate's rating", () => {
    const review = fixture();
    const model = buildCompactComparison(review, ["sql", "etl", "design"], "IM", workspaceSoc);
    const programmingRow = model.rows.find(row => row.label.startsWith("Programming"))!;
    expect(programmingRow.label).toBe("Programming — related to SQL");
    expect(programmingRow.value).toBe(3.38);
    expect(programmingRow.mappings).toEqual([{candidateId: "sql", relation: "related"}]);
    expect(model.rows.find(row => row.label === "ETL")!.value).toBeNull();
    expect(model.rows.find(row => row.label.startsWith("Design"))!.value).toBe(4.2);
    expect(model.scale).toEqual([1, 5]);
    expect(model.occupation?.title).toBe("Database Architects");
    expect(model.release).toBe("30.0");
    expect(resolveOnetRating(review.candidates[0], workspaceSoc, "IM", "30.0").status).toBe("no_association");
  });
  it("requires a choice for distinct descriptors and keeps chosen evidence exact", () => {
    const review = fixture();
    review.candidates[0].onet_associations.push(association("second", "design", "Design", 4.2, "broader"));
    const unresolved = buildCompactComparison(review, ["sql"], "IM", workspaceSoc);
    expect(unresolved.rows[0]).toMatchObject({value: null, status: "ambiguous", evidenceIds: ["programming", "second"]});
    const chosen = buildCompactComparison(review, ["sql"], "IM", workspaceSoc, [{candidate_id: "sql", evidence_id: "second"}]);
    expect(chosen.rows[0]).toMatchObject({label: "Design — broader than SQL", value: 4.2, evidenceIds: ["second"]});
    expect(buildCompactComparison(review, ["sql"], "IM", workspaceSoc, [{candidate_id: "sql", evidence_id: "invalid"}]).rows[0].value).toBeNull();
  });
  it("deduplicates a shared descriptor while retaining per-candidate relations", () => {
    const review = fixture();
    review.candidates[1].onet_associations = [association("programming-other", "programming", "Programming", 3.38, "equivalent")];
    const model = buildCompactComparison(review, ["sql", "etl"], "IM", workspaceSoc);
    expect(model.rows).toHaveLength(1);
    expect(model.rows[0]).toMatchObject({label: "Programming — related to SQL; equivalent to ETL", candidateIds: ["sql", "etl"], evidenceIds: ["programming", "programming-other"],
      mappings: [{candidateId: "sql", relation: "related"}, {candidateId: "etl", relation: "equivalent"}], value: 3.38});
  });
  it.each(["suppressed", "not_relevant", "missing"] as const)("retains %s as unavailable instead of zero", status => {
    const review = fixture();
    review.candidates[0].onet_associations[0].evidence.ratings.IM!.status = status;
    expect(buildCompactComparison(review, ["sql"], "IM", workspaceSoc).rows[0]).toMatchObject({status, value: null});
  });
  it("never borrows another occupation/release or treats a software flag as importance", () => {
    const review = fixture();
    expect(buildCompactComparison(review, ["sql"], "IM", "15-1253.00").rows[0].value).toBeNull();
    expect(buildCompactComparison(review, ["sql"], "IM", "99-9999.00").occupation).toBeNull();
    review.candidates[0].onet_associations[0].evidence.release = "29.0";
    expect(buildCompactComparison(review, ["sql"], "IM", workspaceSoc).rows[0].value).toBeNull();
    review.candidates[0].onet_associations[0] = association("software", "sql", "SQL", 4);
    review.candidates[0].onet_associations[0].evidence.family = "software";
    expect(buildCompactComparison(review, ["sql"], "IM", workspaceSoc).rows[0].value).toBeNull();
  });
  it.each([{scale_id: "LV"}, {minimum: 0}, {maximum: 7}, {value: 0}, {value: Infinity}])("rejects invalid official scale/value %j", patch => {
    const review = fixture();
    Object.assign(review.candidates[0].onet_associations[0].evidence.ratings.IM!, patch);
    expect(buildCompactComparison(review, ["sql"], "IM", workspaceSoc).rows[0].value).toBeNull();
  });
  it("describes a 4/7 sample tie factually and preserves unavailable denominators", () => {
    const review = fixture();
    review.candidates.forEach(candidate => {candidate.job_metrics = {supporting_posting_count: 4, assessed_posting_count: 7, percentage: 57.14, coverage_status: "partial"};});
    const model = buildCompactComparison(review, ["sql", "etl"], "frequency", workspaceSoc);
    expect(model.rows.map(row => row.value)).toEqual([57.14, 57.14]);
    expect(model.rows[0].mappings).toEqual([]);
    expect(model.insight).toMatch(/SQL and ETL.*each.*4 of 7 assessed postings/);
    expect(model.insight).not.toMatch(/market|most demanded/i);
    review.candidates[1].job_metrics.assessed_posting_count = undefined;
    review.candidates[1].job_metrics.percentage = 0;
    expect(buildCompactComparison(review, ["etl"], "frequency", null).rows[0]).toMatchObject({value: null, status: "missing"});
  });
  it("retains every requested comparison without mutating the review or unsafe source links", () => {
    const review = fixture();
    review.candidates = Array.from({length: 7}, (_, index) => ({...review.candidates[0], candidate_id: `skill-${index}`, display_name: `Skill ${index}`}));
    review.candidates[0].qualifying_posting_links = ["javascript:alert(1)"];
    const before = JSON.stringify(review);
    const model = buildCompactComparison(review, review.candidates.map(row => row.candidate_id), "frequency", null);
    expect(model.rows).toHaveLength(7);
    expect(model.rows[0].sourceUrl).toBeNull();
    expect(JSON.stringify(review)).toBe(before);
  });
});
