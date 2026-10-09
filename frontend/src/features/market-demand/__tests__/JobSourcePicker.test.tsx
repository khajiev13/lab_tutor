import {render,screen,fireEvent} from "@testing-library/react";
import {describe,it,expect,vi} from "vitest";
import {JobSourcePicker} from "@/features/market-demand/components/JobSourcePicker";

describe("JobSourcePicker",()=>{
 it("keeps unavailable sources disabled and never selects a fallback",()=>{
  const change=vi.fn();
  render(<JobSourcePicker sources={["headhunter"]} evidenceSources={["jobs"]} catalog={[{id:"indeed",label:"Indeed",availability:"unsupported_country",reason:"Unsupported in Uzbekistan"},{id:"headhunter",label:"HeadHunter",availability:"available",reason:null}]} onSourcesChange={change} onEvidenceChange={vi.fn()} disabled={false}/>);
  expect(screen.getByRole("checkbox",{name:/Indeed/})).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox",{name:/HeadHunter/}));
  expect(change).toHaveBeenCalledWith([]);
  expect(screen.getByText("Unsupported in Uzbekistan")).toBeInTheDocument();
 });
 it("explains job support is required for O*NET-only discovery",()=>{
  render(<JobSourcePicker sources={[]} evidenceSources={["onet"]} catalog={[]} onSourcesChange={vi.fn()} onEvidenceChange={vi.fn()} disabled={false}/>);
  expect(screen.getByText(/supporting job postings.*new analysis/i)).toBeInTheDocument();
 });
});
