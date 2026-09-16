import { useEffect } from 'react';

export function RevealApp() {
  useEffect(() => {
    const splash = document.getElementById('boot-splash');
    const root = document.getElementById('root');
    const frame = requestAnimationFrame(() => {
      root?.removeAttribute('inert');
      window.dispatchEvent(new Event('metiquo:ready'));
      if (!splash) return;
      splash.addEventListener('animationend', (event) => {
        if (event.target === splash) splash.remove();
      });
      splash.dataset.ready = 'true';
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  return null;
}
