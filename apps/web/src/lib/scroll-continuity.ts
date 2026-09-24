export interface ScrollMetrics {
  top: number;
  height: number;
  viewport: number;
}

export interface ScrollSurface {
  read: () => ScrollMetrics;
  reserve: (pixels: number) => void;
  scroll: (top: number) => void;
  reducedMotion: () => boolean;
}

interface FrameClock {
  request: (callback: FrameRequestCallback) => number;
  cancel: (id: number) => void;
}

/** Keep the old scroll range until a shorter surface can settle without a jump. */
export function createScrollContinuity(surface: ScrollSurface, clock: FrameClock) {
  let previous = surface.read();
  let extra = 0;
  let frame = 0;
  let target: number | null = null;
  let paused = false;

  function stop() {
    clock.cancel(frame);
    frame = 0;
  }

  function reset() {
    stop();
    surface.reserve(0);
    extra = 0;
    target = null;
    previous = surface.read();
  }

  function settle(top: number, height: number, naturalHeight: number, viewport: number) {
    stop();
    const end = Math.max(0, naturalHeight - viewport);
    if (top <= end || surface.reducedMotion()) {
      reset();
      return;
    }
    extra = Math.max(height - naturalHeight, top - end);
    surface.reserve(extra);
    // scrollHeight is floored at clientHeight. Very short contents may need
    // more padding than the reported height difference to retain the old top.
    const missing = Math.max(0, top + viewport - surface.read().height);
    if (missing) {
      extra += missing;
      surface.reserve(extra);
    }
    surface.scroll(top);
    previous = surface.read();
    target = end;
    if (paused) return;
    const startExtra = extra;
    const viewportFill = Math.max(0, viewport - (previous.height - extra));
    const duration = Math.min(560, 300 + (top - end) * 0.18);
    let started: number | undefined;
    const tick: FrameRequestCallback = (time) => {
      if (surface.reducedMotion()) {
        reset();
        return;
      }
      started ??= time;
      const progress = Math.min(1, (time - started) / duration);
      const remaining = (1 - progress) ** 3;
      extra = viewportFill + (startExtra - viewportFill) * remaining;
      surface.reserve(extra);
      surface.scroll(end + (top - end) * remaining);
      previous = surface.read();
      if (progress < 1) frame = clock.request(tick);
      else reset();
    };
    frame = clock.request(tick);
  }

  function check(current = surface.read()) {
    if (target !== null && surface.reducedMotion()) {
      reset();
      return;
    }
    const naturalHeight = current.height - extra;
    const max = Math.max(0, naturalHeight - current.viewport);
    if (target !== null) {
      if (Math.abs(max - target) > 1)
        settle(current.top, current.height, naturalHeight, current.viewport);
    } else if (current.height < previous.height - 1 && previous.top > max + 1) {
      settle(previous.top, previous.height, naturalHeight, current.viewport);
    } else previous = current;
  }

  return {
    check,
    reset,
    scroll() {
      // A browser clamp can dispatch scroll before ResizeObserver. Detect it
      // using the previous geometry instead of accepting the jump as user input.
      if (!frame) check();
      if (paused || !frame) previous = surface.read();
    },
    pause() {
      paused = true;
      stop();
    },
    resume() {
      paused = false;
      if (extra) {
        const current = surface.read();
        settle(current.top, current.height, current.height - extra, current.viewport);
      } else check();
    },
    dispose: reset,
  };
}

/** One observer service for the document and any vertical region the user reads. */
export function observeScrollContinuity(document: Document) {
  const view = document.defaultView!;
  const regions = new Map<HTMLElement, ReturnType<typeof createScrollContinuity>>();
  const reduced = view.matchMedia('(prefers-reduced-motion: reduce)');
  let resumeTimer = 0;
  let checking = false;
  let pending = 0;
  const routeKey = () =>
    `${view.location.pathname}:${new URLSearchParams(view.location.search).get('view') ?? ''}`;
  let route = routeKey();

  const check = () => {
    if (checking) return;
    checking = true;
    const navigated = route !== routeKey();
    route = routeKey();
    for (const [element, controller] of regions) {
      if (!element.isConnected) {
        controller.dispose();
        regions.delete(element);
      } else if (navigated) controller.reset();
      else controller.check();
    }
    checking = false;
  };
  const resize = new ResizeObserver(check);
  const observed = new Set<Element>();
  const syncObserved = () => {
    const next = new Set<Element>([document.body]);
    for (const element of regions.keys()) {
      next.add(element);
      for (const child of element.children) next.add(child);
    }
    for (const element of observed) {
      if (!next.has(element)) {
        resize.unobserve(element);
        observed.delete(element);
      }
    }
    for (const element of next) {
      if (!observed.has(element)) {
        resize.observe(element);
        observed.add(element);
      }
    }
  };
  const scheduleCheck = () => {
    if (pending) return;
    pending = view.requestAnimationFrame(() => {
      pending = 0;
      check();
      syncObserved();
    });
  };
  const track = (element: HTMLElement) => {
    if (regions.has(element)) return;
    const inlinePadding = element.style.paddingBottom;
    let basePadding = 0;
    let reserved = 0;
    const anchor = element.style.overflowAnchor;
    const gutter = element.style.scrollbarGutter;
    element.style.overflowAnchor = 'none';
    element.style.scrollbarGutter = 'stable';
    const controller = createScrollContinuity(
      {
        read: () => ({
          top: element.scrollTop,
          height: element.scrollHeight,
          viewport: element.clientHeight,
        }),
        reserve: (pixels) => {
          if (!reserved)
            basePadding = parseFloat(view.getComputedStyle(element).paddingBottom) || 0;
          element.style.paddingBottom = pixels ? `${basePadding + pixels}px` : inlinePadding;
          reserved = pixels;
        },
        scroll: (top) => element.scrollTo({ top, behavior: 'instant' }),
        reducedMotion: () => reduced.matches || document.visibilityState !== 'visible',
      },
      {
        request: (fn) => view.requestAnimationFrame(fn),
        cancel: (id) => view.cancelAnimationFrame(id),
      },
    );
    regions.set(element, {
      ...controller,
      dispose() {
        controller.dispose();
        element.style.overflowAnchor = anchor;
        element.style.scrollbarGutter = gutter;
      },
    });
    syncObserved();
  };
  const root = document.scrollingElement;
  if (root instanceof HTMLElement) track(root);

  const scroll = (event: Event) => {
    const element = event.target === document ? root : event.target;
    if (!(element instanceof HTMLElement)) return;
    if (element.scrollTop > 0) track(element);
    regions.get(element)?.scroll();
  };
  const capture = (event: Event) => {
    for (
      let element = event.target instanceof HTMLElement ? event.target : null;
      element;
      element = element.parentElement
    ) {
      if (element.scrollTop > 0) track(element);
    }
    check();
  };
  const pause = () => {
    for (const controller of regions.values()) controller.pause();
    view.clearTimeout(resumeTimer);
    resumeTimer = view.setTimeout(() => {
      for (const controller of regions.values()) controller.resume();
    }, 160);
  };
  const key = (event: KeyboardEvent) => {
    if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key))
      pause();
  };
  // Text updates are covered by ResizeObserver if their size changes. Observe
  // structural changes once per frame without repeatedly disconnecting it.
  const mutations = new MutationObserver(scheduleCheck);
  mutations.observe(document.body, { subtree: true, childList: true });
  document.addEventListener('scroll', scroll, true);
  document.addEventListener('pointerdown', capture, true);
  document.addEventListener('keydown', key, true);
  document.addEventListener('wheel', pause, { capture: true, passive: true });
  document.addEventListener('touchmove', pause, { capture: true, passive: true });
  document.addEventListener('visibilitychange', check);
  reduced.addEventListener('change', check);
  return () => {
    mutations.disconnect();
    resize.disconnect();
    view.cancelAnimationFrame(pending);
    view.clearTimeout(resumeTimer);
    document.removeEventListener('scroll', scroll, true);
    document.removeEventListener('pointerdown', capture, true);
    document.removeEventListener('keydown', key, true);
    document.removeEventListener('wheel', pause, true);
    document.removeEventListener('touchmove', pause, true);
    document.removeEventListener('visibilitychange', check);
    reduced.removeEventListener('change', check);
    for (const controller of regions.values()) controller.dispose();
  };
}
