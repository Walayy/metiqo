import { useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';

type Detent = 'expanded' | 'compact';

interface Drag {
  pointerId: number;
  startDetent: Detent;
  startY: number;
  startOffset: number;
  height: number;
  offset: number;
  lastY: number;
  lastTime: number;
  velocity: number;
  frame: number | null;
}

export function useMobileSheet(open: boolean, onOpenChange: (open: boolean) => void) {
  const contentRef = useRef<HTMLDivElement>(null);
  const gripRef = useRef<HTMLButtonElement>(null);
  const detentRef = useRef<Detent>('expanded');
  const dragRef = useRef<Drag | null>(null);
  const ignoreClickRef = useRef(false);
  const [detent, setDetent] = useState<Detent>('expanded');

  function compactOffset() {
    const height = contentRef.current?.getBoundingClientRect().height ?? 0;
    const viewport = window.visualViewport?.height ?? window.innerHeight;
    const visible = Math.max(180, Math.min(viewport * 0.56, height * 0.72));
    return Math.max(0, height - visible);
  }

  function setOffset(offset: number) {
    contentRef.current?.style.setProperty('--sheet-offset', `${Math.round(offset)}px`);
  }

  function snap(next: Detent) {
    detentRef.current = next;
    setDetent(next);
    setOffset(next === 'compact' ? compactOffset() : 0);
  }

  useLayoutEffect(() => {
    if (!open) return;
    const sheet = contentRef.current;
    if (!sheet) return;
    detentRef.current = 'expanded';
    setDetent('expanded');
    sheet.dataset.sheetInteracted = 'false';
    sheet.dataset.sheetDragging = 'false';
    sheet.style.setProperty('--sheet-offset', '0px');
    const syncViewport = () => {
      const viewport = window.visualViewport;
      const height = viewport?.height ?? window.innerHeight;
      const bottom = Math.max(0, window.innerHeight - height - (viewport?.offsetTop ?? 0));
      sheet.style.setProperty('--sheet-viewport-height', `${height}px`);
      sheet.style.setProperty('--sheet-viewport-inset', `${bottom}px`);
      if (!dragRef.current && detentRef.current === 'compact') setOffset(compactOffset());
    };
    syncViewport();
    const observer = new ResizeObserver(() => {
      if (!dragRef.current && detentRef.current === 'compact') setOffset(compactOffset());
    });
    observer.observe(sheet);
    window.addEventListener('resize', syncViewport);
    window.visualViewport?.addEventListener('resize', syncViewport);
    window.visualViewport?.addEventListener('scroll', syncViewport);
    return () => {
      window.removeEventListener('resize', syncViewport);
      window.visualViewport?.removeEventListener('resize', syncViewport);
      window.visualViewport?.removeEventListener('scroll', syncViewport);
      observer.disconnect();
      if (dragRef.current?.frame != null) cancelAnimationFrame(dragRef.current.frame);
      dragRef.current = null;
    };
  }, [open]);

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (!event.isPrimary || event.button !== 0 || !contentRef.current) return;
    const sheet = contentRef.current;
    // A grab during the entrance animation starts at the position currently on screen.
    const transform = getComputedStyle(sheet).transform;
    const current = transform === 'none' ? 0 : new DOMMatrixReadOnly(transform).m42;
    sheet.style.setProperty('--sheet-offset', `${current}px`);
    sheet.dataset.sheetInteracted = 'true';
    sheet.dataset.sheetDragging = 'true';
    dragRef.current = {
      pointerId: event.pointerId,
      startDetent: detentRef.current,
      startY: event.clientY,
      startOffset: current,
      height: sheet.getBoundingClientRect().height,
      offset: current,
      lastY: event.clientY,
      lastTime: event.timeStamp,
      velocity: 0,
      frame: null,
    };
    ignoreClickRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const delta = event.clientY - drag.startY;
    if (Math.abs(delta) > 6) ignoreClickRef.current = true;
    const raw = drag.startOffset + delta;
    drag.offset = raw < 0 ? Math.max(-18, raw / 4) : Math.min(drag.height + 40, raw);
    const elapsed = event.timeStamp - drag.lastTime;
    if (elapsed > 0) drag.velocity = (event.clientY - drag.lastY) / elapsed;
    drag.lastY = event.clientY;
    drag.lastTime = event.timeStamp;
    if (drag.frame == null) {
      drag.frame = requestAnimationFrame(() => {
        setOffset(drag.offset);
        drag.frame = null;
      });
    }
  }

  function finish(event: PointerEvent<HTMLButtonElement>, cancelled: boolean) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (drag.frame != null) cancelAnimationFrame(drag.frame);
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
    if (contentRef.current) contentRef.current.dataset.sheetDragging = 'false';
    if (cancelled) {
      snap(detentRef.current);
      return;
    }
    const compact = compactOffset();
    const distance = drag.lastY - drag.startY;
    const moved = Math.abs(distance) > 6;
    const releaseVelocity = event.timeStamp - drag.lastTime < 100 ? drag.velocity : 0;
    const dismiss =
      drag.startDetent === 'compact'
        ? drag.offset > compact + 80 || (releaseVelocity > 1.1 && drag.offset > compact + 42)
        : drag.offset > Math.max(compact + 140, drag.height * 0.78);
    if (moved && dismiss) {
      setOffset(drag.offset);
      onOpenChange(false);
      return;
    }
    if (moved && releaseVelocity > 0.45 && distance > 24) snap('compact');
    else if (moved && releaseVelocity < -0.45 && distance < -24) snap('expanded');
    else snap(drag.offset > compact / 2 ? 'compact' : 'expanded');
  }

  return {
    contentRef,
    gripRef,
    detent,
    expand: () => snap('expanded'),
    onAnimationEnd: () => {
      if (contentRef.current) contentRef.current.dataset.sheetInteracted = 'true';
    },
    onGripClick: () => {
      if (ignoreClickRef.current) {
        ignoreClickRef.current = false;
        return;
      }
      snap(detentRef.current === 'expanded' ? 'compact' : 'expanded');
    },
    onGripKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        snap('expanded');
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        snap('compact');
      }
    },
    onPointerDown,
    onPointerMove,
    onPointerUp: (event: PointerEvent<HTMLButtonElement>) => finish(event, false),
    onPointerCancel: (event: PointerEvent<HTMLButtonElement>) => finish(event, true),
    onLostPointerCapture: (event: PointerEvent<HTMLButtonElement>) => finish(event, true),
  };
}
