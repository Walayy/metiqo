import { useSyncExternalStore } from 'react';
type Theme = 'light' | 'dark';
const themeEvent = 'metiquo:themechange';
function subscribe(callback: () => void) {
  const media = matchMedia('(prefers-color-scheme: dark)');
  function sync() {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem('metiquo:theme');
    } catch {
      /* System preference. */
    }
    apply(saved === 'light' || saved === 'dark' ? saved : media.matches ? 'dark' : 'light');
    callback();
  }
  window.addEventListener(themeEvent, callback);
  window.addEventListener('storage', sync);
  media.addEventListener('change', sync);
  return () => {
    window.removeEventListener(themeEvent, callback);
    window.removeEventListener('storage', sync);
    media.removeEventListener('change', sync);
  };
}
function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document
    .querySelector<HTMLLinkElement>('#brand-favicon')
    ?.setAttribute('href', `/brand/${theme}/favicon.ico`);
  document
    .querySelector<HTMLLinkElement>('#brand-touch-icon')
    ?.setAttribute('href', `/brand/${theme}/apple-touch-icon.png`);
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'dark' ? '#111411' : '#f6f7f5');
}
export function useTheme() {
  const theme = useSyncExternalStore(
    subscribe,
    () => document.documentElement.dataset.theme as Theme,
    () => 'light' as Theme,
  );
  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark';
    apply(next);
    try {
      localStorage.setItem('metiquo:theme', next);
    } catch {
      /* In-memory preference remains applied. */
    }
    window.dispatchEvent(new Event(themeEvent));
  }
  return { theme, toggleTheme };
}
