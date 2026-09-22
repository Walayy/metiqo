import { useEffect } from 'react';
import { observeScrollContinuity } from '@/lib/scroll-continuity';

export function ScrollContinuity() {
  useEffect(() => observeScrollContinuity(document), []);
  return null;
}
