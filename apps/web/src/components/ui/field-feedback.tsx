import { motion, useReducedMotion } from 'motion/react';
import './field-feedback.css';

interface Props {
  id: string;
  message: string;
  tone?: 'hint' | 'error' | 'success';
  reserve: readonly string[];
}

export function FieldFeedback({ id, message, tone = 'hint', reserve }: Props) {
  const reducedMotion = useReducedMotion();
  return (
    <div className="field-feedback">
      {/* Measure every possible message at the actual font size and available width.
          These inaccessible copies reserve space without clipping or fixed heights. */}
      {reserve.map((text) => (
        <span key={text} className="field-feedback-measure" aria-hidden="true">
          {text}
        </span>
      ))}
      <div
        id={id}
        className="field-feedback-content"
        aria-live={tone === 'hint' ? 'off' : 'polite'}
        aria-atomic="true"
      >
        <motion.p
          key={tone}
          className={`field-feedback-message field-feedback-message--${tone}`}
          initial={reducedMotion ? false : { opacity: 0.3, y: 2 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reducedMotion ? 0 : 0.16, ease: 'easeOut' }}
        >
          {message}
        </motion.p>
      </div>
    </div>
  );
}
