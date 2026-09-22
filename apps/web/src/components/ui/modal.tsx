import { Dialog } from 'radix-ui';
import { X } from 'lucide-react';
import { useRef } from 'react';
import type { ReactNode, RefObject } from 'react';
import { Button } from './button';
interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description: string;
  children: ReactNode;
  className?: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  className = '',
  initialFocusRef,
}: Props) {
  const opener = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          className={`modal-content ${className}`}
          onOpenAutoFocus={(event) => {
            opener.current =
              document.activeElement instanceof HTMLElement ? document.activeElement : null;
            if (initialFocusRef?.current) {
              event.preventDefault();
              initialFocusRef.current.focus();
            }
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
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
                : (document.getElementById('values-title') ??
                  document.getElementById('main-content'));
              fallback?.focus({ preventScroll: true });
            }
          }}
        >
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
