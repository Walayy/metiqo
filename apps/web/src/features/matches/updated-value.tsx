import { useContext, useLayoutEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { highlightObservation } from './visible-update';
import { ObservationScope } from './observation-scope';

/** Animate a changed observation only; mounting or ticking the clock is silent. */
export function UpdatedValue({
  value,
  children,
  className = '',
}: {
  value: string | number | null | undefined;
  children?: ReactNode;
  className?: string;
}) {
  const element = useRef<HTMLSpanElement>(null);
  const previous = useRef(value);
  const scope = useContext(ObservationScope);
  const previousScope = useRef(scope);
  useLayoutEffect(() => {
    const changed = previous.current !== value && previousScope.current === scope;
    previousScope.current = scope;
    // Offscreen observations still replace the baseline: scrolling into view
    // must never replay a change the user did not witness.
    previous.current = value;
    if (changed && element.current) return highlightObservation(element.current);
  }, [value, scope]);
  return (
    <span ref={element} className={`observed-value ${className}`}>
      {children ?? value}
    </span>
  );
}
