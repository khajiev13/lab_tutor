import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {createMemoryRouter, Link, RouterProvider, useLocation} from 'react-router-dom';
import {useWorkspaceNavigationGuard} from '@/features/market-demand/hooks/useWorkspaceNavigationGuard';
import {reviewFixture} from '@/features/market-demand/__tests__/review-fixtures';
const routers: ReturnType<typeof createMemoryRouter>[] = [];
afterEach(() => {cleanup(); routers.splice(0).forEach(router => router.dispose());});
function setup(save = vi.fn(async () => reviewFixture()), dirty = true) {
 function Harness() {
  const guard = useWorkspaceNavigationGuard({dirty, save});
  return <><p>{useLocation().pathname}</p><Link to="/next">Leave</Link><Link to="/replacement">Replacement</Link>{guard.blockedDestination && <><button onClick={() => void guard.saveAndLeave().catch(() => {})}>Save</button><button onClick={guard.discardAndLeave}>Discard</button><button onClick={guard.stay}>Cancel</button></>}</>;
 }
 const router = createMemoryRouter([{path:'*',element:<Harness/>}], {initialEntries:['/previous','/workspace']});
 routers.push(router); render(<RouterProvider router={router}/>); return {router, save};
}
describe('workspace navigation protection', () => {
 it('does not let a late save proceed to a replacement blocked destination', async () => {
  let finish!: () => void;
  const save=vi.fn(() => new Promise<ReturnType<typeof reviewFixture>>(resolve => {finish=()=>resolve(reviewFixture());}));
  const {router}=setup(save);
  fireEvent.click(screen.getByText('Leave')); fireEvent.click(await screen.findByText('Save'));
  fireEvent.click(screen.getByText('Replacement'));
  await act(async () => finish());
  expect(router.state.location.pathname).toBe('/workspace');
  fireEvent.click(screen.getByText('Discard'));
  await waitFor(() => expect(router.state.location.pathname).toBe('/replacement'));
 });
 it('blocks a dirty link and Cancel retains the current path', async () => {const {router} = setup(); fireEvent.click(screen.getByText('Leave')); await screen.findByText('Cancel'); fireEvent.click(screen.getByText('Cancel')); expect(router.state.location.pathname).toBe('/workspace');});
 it('blocks history back and Discard proceeds to the exact destination', async () => {const {router} = setup(); await act(async () => {await router.navigate(-1);}); await screen.findByText('Discard'); fireEvent.click(screen.getByText('Discard')); await waitFor(() => expect(router.state.location.pathname).toBe('/previous'));});
 it('waits for acknowledged save before leaving', async () => {let finish!: () => void; const save = vi.fn(() => new Promise<ReturnType<typeof reviewFixture>>(resolve => {finish = () => resolve(reviewFixture());})); const {router} = setup(save); fireEvent.click(screen.getByText('Leave')); fireEvent.click(await screen.findByText('Save')); expect(router.state.location.pathname).toBe('/workspace'); await act(async () => finish()); await waitFor(() => expect(router.state.location.pathname).toBe('/next'));});
 it('keeps the blocked page when save rejects', async () => {const {router,save} = setup(vi.fn(async () => {throw new Error('offline');})); fireEvent.click(screen.getByText('Leave')); fireEvent.click(await screen.findByText('Save')); await waitFor(() => expect(save).toHaveBeenCalledOnce()); expect(router.state.location.pathname).toBe('/workspace'); expect(screen.getByText('Cancel')).toBeInTheDocument();});
 it('requests native unload confirmation only for dirty state', () => {setup(); const event = new Event('beforeunload',{cancelable:true}); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true);});
 it('allows clean navigation', async () => {const {router} = setup(undefined,false); fireEvent.click(screen.getByText('Leave')); await waitFor(() => expect(router.state.location.pathname).toBe('/next'));});
});
