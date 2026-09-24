import { Dialog } from 'radix-ui';
import { X } from 'lucide-react';
import { useRef } from 'react';
import type { ReactNode, RefObject } from 'react';
import { Button } from './button';
import { useMobileSheet } from './use-mobile-sheet';
interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description: string;
  children: ReactNode;
  className?: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
  returnFocus?: boolean;
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  className = '',
  initialFocusRef,
  returnFocus = true,
}: Props) {
  const opener = useRef<HTMLElement | null>(null);
  const {
    contentRef,
    gripRef,
    onAnimationEnd,
    onGripClick,
    onGripKeyDown,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    onLostPointerCapture,
  } = useMobileSheet(open, onOpenChange);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          ref={contentRef}
          className={`modal-content ${className}`}
          data-mobile-sheet="true"
          onAnimationEnd={(event) => {
            if (event.target === event.currentTarget) onAnimationEnd();
          }}
          onOpenAutoFocus={(event) => {
            opener.current =
              document.activeElement instanceof HTMLElement ? document.activeElement : null;
            if (window.matchMedia('(max-width: 680px)').matches && gripRef.current) {
              event.preventDefault();
              gripRef.current.focus({ preventScroll: true });
            } else if (initialFocusRef?.current) {
              event.preventDefault();
              initialFocusRef.current.focus();
            }
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (!returnFocus) return;
            if (
              opener.current?.isConnected &&
              opener.current !== document.body &&
              opener.current.getClientRects().length > 0
            )
              opener.current.focus({ preventScroll: true });
            else {
              const navigation = document.querySelector<HTMLButtonElement>(
                '[aria-label="Ouvrir la navigation"]',
              );
              const fallback = navigation?.getClientRects().length
                ? navigation
                : (document.getElementById('matches-title') ??
                  document.getElementById('values-title') ??
                  document.getElementById('main-content'));
              fallback?.focus({ preventScroll: true });
            }
          }}
        >
          <button
            ref={gripRef}
            type="button"
            className="modal-sheet-grip"
            aria-label="Fermer la fenêtre, glisser vers le bas"
            onClick={onGripClick}
            onKeyDown={onGripKeyDown}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerCancel}
            onLostPointerCapture={onLostPointerCapture}
          />
          <div className="modal-header">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Description>{description}</Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button iconOnly variant="ghost" aria-label="Fermer">
                <X size={20} />
              </Button>
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
