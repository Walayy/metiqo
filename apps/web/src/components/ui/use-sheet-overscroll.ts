import { useLayoutEffect } from 'react';
import type { RefObject } from 'react';

interface TouchGesture {
  identifier: number;
  scroller: HTMLElement;
  startX: number;
  startY: number;
  lastY: number;
  pull: number;
  horizontal: boolean;
}

function scrollContainer(target: EventTarget | null, sheet: HTMLElement) {
  let element = target instanceof Element ? target : null;
  while (element && element !== sheet) {
    if (element instanceof HTMLElement) {
      const overflow = getComputedStyle(element).overflowY;
      if ((overflow === 'auto' || overflow === 'scroll') && element.clientHeight > 0)
        return element;
    }
    element = element.parentElement;
  }
  return null;
}

function visualPull(distance: number) {
  return Math.sign(distance) * 48 * (Math.sqrt(1 + Math.abs(distance) / 48) - 1);
}

function rawPull(distance: number) {
  return Math.sign(distance) * (2 * Math.abs(distance) + (distance * distance) / 48);
}

function currentPull(scroller: HTMLElement) {
  const firstChild = scroller.firstElementChild;
  if (!firstChild) return 0;
  const translate = getComputedStyle(firstChild).translate;
  return Number.parseFloat(translate.split(' ')[1] ?? '0') || 0;
}

export function useSheetOverscroll(
  open: boolean,
  contentRef: RefObject<HTMLDivElement | null>,
  contentMounted: boolean,
) {
  useLayoutEffect(() => {
    const sheet = contentRef.current;
    if (!open || !sheet) return;
    const activeSheet = sheet;
    const mobileViewport = window.matchMedia('(max-width: 680px)');
    let gesture: TouchGesture | null = null;
    const settleTimers = new Map<HTMLElement, number>();

    function clearSettled(scroller: HTMLElement) {
      const timer = settleTimers.get(scroller);
      if (timer !== undefined) window.clearTimeout(timer);
      settleTimers.delete(scroller);
    }

    function restore(scroller: HTMLElement) {
      clearSettled(scroller);
      delete scroller.dataset.sheetScrollElastic;
      delete scroller.dataset.sheetScrollPulling;
      scroller.style.removeProperty('--sheet-scroll-pull');
    }

    function release() {
      if (!gesture) return;
      const scroller = gesture.scroller;
      gesture = null;
      if (scroller.dataset.sheetScrollPulling !== 'true') return;
      scroller.dataset.sheetScrollPulling = 'false';
      // Commit the dragged position before starting the return transition.
      if (scroller.firstElementChild) void getComputedStyle(scroller.firstElementChild).translate;
      scroller.style.setProperty('--sheet-scroll-pull', '0px');
      clearSettled(scroller);
      settleTimers.set(
        scroller,
        window.setTimeout(
          () => restore(scroller),
          window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 460,
        ),
      );
    }

    function onStart(event: TouchEvent) {
      release();
      if (!mobileViewport.matches || event.touches.length !== 1) return;
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(
          'input, textarea, select, [contenteditable]:not([contenteditable="false"]), .modal-sheet-grip',
        )
      )
        return;
      const scroller = scrollContainer(target, activeSheet);
      if (!scroller) return;
      clearSettled(scroller);
      const touch = event.touches[0];
      if (!touch) return;
      const visible = currentPull(scroller);
      if (visible !== 0) {
        scroller.dataset.sheetScrollElastic = 'true';
        scroller.dataset.sheetScrollPulling = 'true';
        scroller.style.setProperty('--sheet-scroll-pull', `${visible}px`);
      }
      gesture = {
        identifier: touch.identifier,
        scroller,
        startX: touch.clientX,
        startY: touch.clientY,
        lastY: touch.clientY,
        pull: rawPull(visible),
        horizontal: false,
      };
    }

    function onMove(event: TouchEvent) {
      if (!gesture) return;
      if (!mobileViewport.matches) {
        restore(gesture.scroller);
        gesture = null;
        return;
      }
      if (event.touches.length !== 1) {
        release();
        return;
      }
      const touch = Array.from(event.touches).find(
        (item) => item.identifier === gesture?.identifier,
      );
      if (!touch) return;
      const step = touch.clientY - gesture.lastY;
      gesture.lastY = touch.clientY;
      const totalY = touch.clientY - gesture.startY;
      const totalX = touch.clientX - gesture.startX;
      if (gesture.horizontal) return;
      if (gesture.pull === 0 && Math.abs(totalX) > Math.abs(totalY) && Math.abs(totalX) > 4) {
        gesture.horizontal = true;
        return;
      }
      if (gesture.pull === 0 && (Math.abs(totalY) < 4 || Math.abs(totalY) < Math.abs(totalX)))
        return;

      const scroller = gesture.scroller;
      const maxScroll = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
      const next = gesture.pull + step;
      const pullingTop = next > 0 && scroller.scrollTop <= 1;
      const pullingBottom = next < 0 && scroller.scrollTop >= maxScroll - 1;
      if (!pullingTop && !pullingBottom) {
        if (gesture.pull !== 0) {
          gesture.pull = 0;
          scroller.style.setProperty('--sheet-scroll-pull', '0px');
          if (event.cancelable) event.preventDefault();
        }
        return;
      }
      gesture.pull = next;
      scroller.dataset.sheetScrollElastic = 'true';
      scroller.dataset.sheetScrollPulling = 'true';
      scroller.style.setProperty('--sheet-scroll-pull', `${visualPull(next)}px`);
      if (event.cancelable) event.preventDefault();
    }

    function onEnd(event: TouchEvent) {
      if (
        gesture &&
        Array.from(event.changedTouches).some((touch) => touch.identifier === gesture?.identifier)
      )
        release();
    }

    sheet.addEventListener('touchstart', onStart, { capture: true, passive: true });
    sheet.addEventListener('touchmove', onMove, { capture: true, passive: false });
    sheet.addEventListener('touchend', onEnd, { capture: true, passive: true });
    sheet.addEventListener('touchcancel', onEnd, { capture: true, passive: true });
    return () => {
      sheet.removeEventListener('touchstart', onStart, true);
      sheet.removeEventListener('touchmove', onMove, true);
      sheet.removeEventListener('touchend', onEnd, true);
      sheet.removeEventListener('touchcancel', onEnd, true);
      if (gesture) restore(gesture.scroller);
      for (const scroller of settleTimers.keys()) restore(scroller);
    };
  }, [open, contentMounted, contentRef]);
}
