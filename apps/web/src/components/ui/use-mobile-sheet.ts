import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';
import { useSheetOverscroll } from './use-sheet-overscroll';

interface Drag {
  pointerId: number;
  startY: number;
  startOffset: number;
  height: number;
  offset: number;
  lastY: number;
  lastTime: number;
  velocity: number;
  lastDirection: 'up' | 'down' | null;
  frame: number | null;
}

export function useMobileSheet(open: boolean, onOpenChange: (open: boolean) => void) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentMounted, setContentMounted] = useState(false);
  const attachContent = useCallback((node: HTMLDivElement | null) => {
    contentRef.current = node;
    setContentMounted(node !== null);
  }, []);
  const gripRef = useRef<HTMLButtonElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const ignoreClickRef = useRef(false);
  useSheetOverscroll(open, contentRef, contentMounted);

  function setOffset(offset: number) {
    contentRef.current?.style.setProperty('--sheet-offset', `${Math.round(offset)}px`);
  }

  useLayoutEffect(() => {
    if (!open) return;
    const sheet = contentRef.current;
    if (!sheet) return;
    sheet.dataset.sheetInteracted = 'false';
    sheet.dataset.sheetDragging = 'false';
    sheet.style.setProperty('--sheet-offset', '0px');
    const syncViewport = () => {
      const viewport = window.visualViewport;
      const height = viewport?.height ?? window.innerHeight;
      const bottom = Math.max(0, window.innerHeight - height - (viewport?.offsetTop ?? 0));
      sheet.style.setProperty('--sheet-viewport-height', `${height}px`);
      sheet.style.setProperty('--sheet-viewport-inset', `${bottom}px`);
    };
    syncViewport();
    window.addEventListener('resize', syncViewport);
    window.visualViewport?.addEventListener('resize', syncViewport);
    window.visualViewport?.addEventListener('scroll', syncViewport);
    return () => {
      window.removeEventListener('resize', syncViewport);
      window.visualViewport?.removeEventListener('resize', syncViewport);
      window.visualViewport?.removeEventListener('scroll', syncViewport);
      if (dragRef.current?.frame != null) cancelAnimationFrame(dragRef.current.frame);
      dragRef.current = null;
    };
  }, [open, contentMounted]);

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (!event.isPrimary || event.button !== 0 || !contentRef.current) return;
    const sheet = contentRef.current;
    // A grab during the entrance animation starts exactly where the sheet is visible.
    const transform = getComputedStyle(sheet).transform;
    const current = transform === 'none' ? 0 : new DOMMatrixReadOnly(transform).m42;
    sheet.style.setProperty('--sheet-offset', `${current}px`);
    sheet.dataset.sheetInteracted = 'true';
    sheet.dataset.sheetDragging = 'true';
    dragRef.current = {
      pointerId: event.pointerId,
      startY: event.clientY,
      startOffset: current,
      height: sheet.getBoundingClientRect().height,
      offset: current,
      lastY: event.clientY,
      lastTime: event.timeStamp,
      velocity: 0,
      lastDirection: null,
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
    drag.offset = raw < 0 ? Math.max(-18, raw / 4) : Math.min(drag.height, raw);
    const elapsed = event.timeStamp - drag.lastTime;
    const step = event.clientY - drag.lastY;
    if (Math.abs(step) >= 1) drag.lastDirection = step < 0 ? 'up' : 'down';
    if (elapsed > 0) drag.velocity = step / elapsed;
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
      setOffset(0);
      return;
    }
    const finalStep = event.clientY - drag.lastY;
    if (Math.abs(finalStep) >= 1) drag.lastDirection = finalStep < 0 ? 'up' : 'down';
    // The release direction wins over the total pull: a reversal reopens the sheet.
    if (drag.lastDirection === 'up') {
      setOffset(0);
      return;
    }
    const distance = event.clientY - drag.startY;
    const releaseVelocity = event.timeStamp - drag.lastTime < 100 ? drag.velocity : 0;
    const threshold = Math.min(112, Math.max(72, drag.height * 0.16));
    if (distance > threshold || (distance > 24 && releaseVelocity > 0.6)) {
      setOffset(drag.offset);
      onOpenChange(false);
    } else {
      setOffset(0);
    }
  }

  return {
    contentRef: attachContent,
    gripRef,
    onAnimationEnd: () => {
      if (contentRef.current) contentRef.current.dataset.sheetInteracted = 'true';
    },
    onGripClick: () => {
      if (ignoreClickRef.current) {
        ignoreClickRef.current = false;
        return;
      }
      onOpenChange(false);
    },
    onGripKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        onOpenChange(false);
      }
    },
    onPointerDown,
    onPointerMove,
    onPointerUp: (event: PointerEvent<HTMLButtonElement>) => finish(event, false),
    onPointerCancel: (event: PointerEvent<HTMLButtonElement>) => finish(event, true),
    onLostPointerCapture: (event: PointerEvent<HTMLButtonElement>) => finish(event, true),
  };
}
