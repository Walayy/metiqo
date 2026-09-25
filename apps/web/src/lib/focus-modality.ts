const keyboardNavigationKeys = new Set([
  'Tab',
  'Enter',
  'Escape',
  ' ',
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'Home',
  'End',
  'PageUp',
  'PageDown',
]);

export function trackFocusModality() {
  const root = document.documentElement;
  let lastPointerDown = -Infinity;

  // Browsers can carry keyboard :focus-visible through an automatic focus move
  // caused by a tap, such as the mobile dialog grip receiving focus.
  document.addEventListener(
    'pointerdown',
    () => {
      lastPointerDown = performance.now();
      root.dataset.focusModality = 'pointer';
    },
    true,
  );

  document.addEventListener(
    'keydown',
    (event) => {
      if (keyboardNavigationKeys.has(event.key)) delete root.dataset.focusModality;
    },
    true,
  );

  document.addEventListener(
    'focusin',
    () => {
      // A later focus move without a recent pointer action can come from
      // assistive technology or script. Let the browser decide its indicator.
      if (performance.now() - lastPointerDown > 500) delete root.dataset.focusModality;
    },
    true,
  );

  document.addEventListener(
    'click',
    (event) => {
      // Screen readers commonly activate controls with a synthetic click.
      if (event.detail === 0 && performance.now() - lastPointerDown > 500)
        delete root.dataset.focusModality;
    },
    true,
  );
}
