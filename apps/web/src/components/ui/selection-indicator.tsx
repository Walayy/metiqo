import { motion, useReducedMotion } from 'motion/react';

export function SelectionIndicator({ id }: { id: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.span
      className="selection-indicator"
      layoutId={reduced ? undefined : id}
      aria-hidden="true"
      transition={{ type: 'spring', stiffness: 420, damping: 38 }}
    />
  );
}
