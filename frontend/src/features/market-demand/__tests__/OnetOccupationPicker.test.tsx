import {act,render,screen,fireEvent,waitFor} from "@testing-library/react";
import {beforeEach,it,expect,vi} from "vitest";
import {OnetOccupationPicker} from "@/features/market-demand/components/OnetOccupationPicker";
import {fetchOnetReleases,searchOnetOccupations} from "@/features/market-demand/api";
vi.mock("@/features/market-demand/api",()=>({fetchOnetReleases:vi.fn(),searchOnetOccupations:vi.fn()}));
beforeEach(()=>{vi.mocked(fetchOnetReleases).mockResolvedValue({items:[{version:"31.0",active:true,attribution:"O*NET"}]});vi.mocked(searchOnetOccupations).mockResolvedValue({items:[{soc_code:"15-2051.00",title:"Data Scientists",description:"Analyze data"}],total:1,release:"31.0"});});
it("requires explicit occupation confirmation",async()=>{
 const confirm=vi.fn();
 render(<OnetOccupationPicker courseId={1} release="31.0" selectedCodes={[]} disabled={false} onReleaseChange={vi.fn()} onConfirm={confirm}/>);
 await waitFor(()=>expect(screen.getByRole("checkbox",{name:/Data Scientists/})).toBeInTheDocument());
 expect(screen.getByRole("button",{name:/Confirm occupations/})).toBeDisabled();
 fireEvent.click(screen.getByRole("checkbox",{name:/Data Scientists/}));
 expect(confirm).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:/Confirm occupations/}));
 await waitFor(()=>expect(confirm).toHaveBeenCalledWith("31.0",["15-2051.00"]));
});
it("shows unavailable catalog instead of claiming no matching occupations",async()=>{
 vi.mocked(fetchOnetReleases).mockRejectedValue(new Error("Catalog unavailable"));
 render(<OnetOccupationPicker courseId={1} release={null} selectedCodes={[]} disabled={false} onReleaseChange={vi.fn()} onConfirm={vi.fn()}/>);
 expect(await screen.findByText(/Catalog unavailable/)).toBeInTheDocument();
 expect(screen.queryByText(/No matching occupations/)).not.toBeInTheDocument();
});

it("preserves restored confirmed codes even when they are outside search results",async()=>{
 const confirm=vi.fn();
 render(<OnetOccupationPicker courseId={1} release="31.0" selectedCodes={["15-1252.00"]} disabled={false} onReleaseChange={vi.fn()} onConfirm={confirm}/>);
 await screen.findByRole("checkbox",{name:/Data Scientists/});
 fireEvent.click(screen.getByRole("button",{name:/Confirm occupations/}));
 await waitFor(()=>expect(confirm).toHaveBeenCalledWith("31.0",["15-1252.00"]));
});

it("locks the release and search while occupation confirmation is pending", async () => {
  let finish!: () => void;
  const confirm = vi.fn(() => new Promise<void>(resolve => {finish = resolve;}));
  render(<OnetOccupationPicker courseId={1} release="31.0" selectedCodes={["15-2051.00"]} disabled={false} onReleaseChange={vi.fn()} onConfirm={confirm}/>);
  await screen.findByRole("checkbox", {name:/Data Scientists/});
  fireEvent.click(screen.getByRole("button", {name:"Confirm occupations"}));
  await waitFor(() => expect(confirm).toHaveBeenCalled());
  expect(screen.getByRole("combobox", {name:"O*NET release"})).toBeDisabled();
  expect(screen.getByRole("textbox", {name:"Search occupations"})).toBeDisabled();
  await act(async () => {finish();});
});
