/** Test the painted portion, including scroll containers and covering dialogs. */
export function isObservationVisible(element: HTMLElement): boolean {
  const document = element.ownerDocument;
  const view = document.defaultView;
  if (!view || document.visibilityState !== 'visible' || !element.isConnected) return false;
  if (element.closest('[hidden], [inert], [aria-hidden="true"]')) return false;
  const rect = element.getBoundingClientRect();
  let left = Math.max(0, rect.left);
  let right = Math.min(view.innerWidth, rect.right);
  let top = Math.max(0, rect.top);
  let bottom = Math.min(view.innerHeight, rect.bottom);
  if (right - left < 2 || bottom - top < 2) return false;
  for (let parent: HTMLElement | null = element; parent; parent = parent.parentElement) {
    const style = view.getComputedStyle(parent);
    if (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity) === 0)
      return false;
    if (parent === element) continue;
    const bounds = parent.getBoundingClientRect();
    if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
      left = Math.max(left, bounds.left);
      right = Math.min(right, bounds.right);
    }
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
      top = Math.max(top, bounds.top);
      bottom = Math.min(bottom, bounds.bottom);
    }
  }
  if (right - left < 2 || bottom - top < 2) return false;
  // Sampling several points admits partly visible values, while sticky tabs,
  // popovers and modal backdrops correctly hide values beneath them.
  return [0.25, 0.5, 0.75].some((fraction) => {
    const hit = document.elementFromPoint(
      left + (right - left) * fraction,
      top + (bottom - top) / 2,
    );
    return hit !== null && element.contains(hit);
  });
}

export function highlightObservation(element: HTMLElement): (() => void) | undefined {
  const view = element.ownerDocument.defaultView;
  if (
    !view ||
    view.matchMedia('(prefers-reduced-motion: reduce)').matches ||
    !isObservationVisible(element)
  )
    return;
  const animation = element.animate(
    [
      { backgroundColor: 'var(--accent-soft)', boxShadow: '0 0 0 3px var(--accent-soft)' },
      { backgroundColor: 'transparent', boxShadow: '0 0 0 3px transparent' },
    ],
    { duration: 1200, easing: 'ease-out' },
  );
  element.dataset.updated = 'true';
  const cleanup = () => {
    delete element.dataset.updated;
    animation.cancel();
    view.removeEventListener('scroll', cleanup, true);
    view.removeEventListener('resize', check);
    view.removeEventListener('pointerdown', cleanup, true);
    view.removeEventListener('keydown', cleanup, true);
    element.ownerDocument.removeEventListener('visibilitychange', check);
  };
  const check = () => {
    if (!isObservationVisible(element)) cleanup();
  };
  animation.onfinish = cleanup;
  // The reader's scroll ends the transient highlight. No per-value geometry
  // walk or hit-testing on the scroll path, and nothing replays when returning.
  view.addEventListener('scroll', cleanup, { capture: true, passive: true });
  view.addEventListener('resize', check);
  view.addEventListener('pointerdown', cleanup, true);
  view.addEventListener('keydown', cleanup, true);
  element.ownerDocument.addEventListener('visibilitychange', check);
  return cleanup;
}
