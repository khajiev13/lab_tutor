import { describe, it, expect } from "vitest";
import { AGENT_IDENTITIES } from "../agent-config";
import type { AgentName } from "../types";

describe("AGENT_IDENTITIES", () => {
  const agents: AgentName[] = ["supervisor", "curriculum_mapper", "concept_linker"];

  it("has an identity for every AgentName", () => {
    for (const name of agents) {
      expect(AGENT_IDENTITIES[name]).toBeDefined();
    }
  });

  it.each(agents)("%s has all required fields", (name) => {
    const identity = AGENT_IDENTITIES[name];
    expect(identity.displayName).toBeTruthy();
    expect(identity.shortName).toBeTruthy();
    expect(identity.icon).toBeDefined();
    expect(identity.accentColor).toBeTruthy();
    expect(identity.bgColor).toBeTruthy();
    expect(identity.borderColor).toBeTruthy();
  });

  it("supervisor has blue accent", () => {
    expect(AGENT_IDENTITIES.supervisor.accentColor).toContain("blue");
  });

  it("curriculum_mapper has emerald accent", () => {
    expect(AGENT_IDENTITIES.curriculum_mapper.accentColor).toContain("emerald");
  });

  it("concept_linker has amber accent", () => {
    expect(AGENT_IDENTITIES.concept_linker.accentColor).toContain("amber");
  });
});
