import type { ReactNode } from 'react';
import { motion, useReducedMotion } from 'motion/react';

/** Only the result region changes; controls and keyboard focus stay in place. */
export function ContentTransition({
  children,
  id,
  className,
}: {
  children: ReactNode;
  id: string;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      key={id}
      className={className}
      initial={reduced ? false : { opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
