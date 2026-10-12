import {useCallback, useLayoutEffect, useRef, useState} from 'react';
import {useBeforeUnload, useBlocker} from 'react-router-dom';
import type {SkillReview} from '@/features/market-demand/types';

export function useWorkspaceNavigationGuard({dirty, save}: {dirty: boolean; save: () => Promise<SkillReview>}) {
 const blocker = useBlocker(dirty);
 const [saving, setSaving] = useState(false);
 const [error, setError] = useState<string | null>(null);
 const latest = useRef({blocker, save});
 const pending = useRef(false);
 useLayoutEffect(() => {latest.current = {blocker,save};});
 useBeforeUnload(useCallback((event: BeforeUnloadEvent) => {
  if (!dirty) return;
  event.preventDefault(); event.returnValue = '';
 }, [dirty]));
 const saveAndLeave = async () => {
  if (pending.current || blocker.state !== 'blocked') return;
  const destination = blocker.location.key;
  pending.current = true; setSaving(true); setError(null);
  try {
   await latest.current.save();
   const current = latest.current.blocker;
   if (current.state === 'blocked' && current.location.key === destination) current.proceed();
  } catch (cause) {
   setError(cause instanceof Error ? cause.message : 'Draft could not be saved'); throw cause;
  } finally {pending.current = false; setSaving(false);}
 };
 return {
  blockedDestination: blocker.state === 'blocked' ? blocker.location : null, saving, error, saveAndLeave,
  discardAndLeave: () => {if (!pending.current && blocker.state === 'blocked') blocker.proceed();},
  stay: () => {if (!pending.current && blocker.state === 'blocked') {setError(null); blocker.reset();}},
 };
}
