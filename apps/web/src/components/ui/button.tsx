import { forwardRef } from 'react';
import type { ButtonHTMLAttributes } from 'react';
import { clsx } from 'clsx';
type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost';
  iconOnly?: boolean;
};
export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { className, variant = 'secondary', iconOnly = false, type = 'button', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={clsx('button', `button--${variant}`, iconOnly && 'icon-button', className)}
      {...props}
    />
  );
});
