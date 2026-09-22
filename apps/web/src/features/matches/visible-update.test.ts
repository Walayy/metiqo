import { describe, expect, it, vi } from 'vitest';
import { highlightObservation, isObservationVisible } from './visible-update';

function surface() {
  const rect = { left: 20, top: 20, right: 100, bottom: 40 };
  const style = {
    visibility: 'visible',
    display: 'inline',
    opacity: '1',
    overflowX: 'visible',
    overflowY: 'visible',
  };
  const view = Object.assign(new EventTarget(), {
    innerWidth: 390,
    innerHeight: 844,
    getComputedStyle: () => style,
    matchMedia: () => ({ matches: false }),
  });
  const animation = { cancel: vi.fn(), onfinish: null as (() => void) | null };
  const document = Object.assign(new EventTarget(), {
    visibilityState: 'visible',
    defaultView: view,
    elementFromPoint: vi.fn(),
  });
  const value = {
    ownerDocument: document,
    isConnected: true,
    dataset: {} as Record<string, string>,
    closest: vi.fn(),
    getBoundingClientRect: () => rect,
    contains: (hit: unknown) => hit === value,
    parentElement: null as unknown,
    animate: vi.fn(() => animation),
  };
  document.elementFromPoint.mockReturnValue(value);
  return {
    element: value as unknown as HTMLElement,
    value,
    rect,
    style,
    view,
    document,
    animation,
  };
}

describe('surbrillance des données effectivement visibles', () => {
  it('exclut le hors-écran, les onglets masqués et les valeurs derrière la modale', () => {
    const s = surface();
    expect(isObservationVisible(s.element)).toBe(true);
    s.rect.top = 900;
    s.rect.bottom = 920;
    expect(highlightObservation(s.element)).toBeUndefined();
    s.rect.top = 20;
    s.rect.bottom = 40;
    s.document.visibilityState = 'hidden';
    expect(highlightObservation(s.element)).toBeUndefined();
    s.document.visibilityState = 'visible';
    s.document.elementFromPoint.mockReturnValue({ overlay: true });
    expect(highlightObservation(s.element)).toBeUndefined();
    expect(s.value.animate).not.toHaveBeenCalled();
  });
  it('respecte les conteneurs défilants même dans le viewport', () => {
    const s = surface();
    s.value.parentElement = {
      parentElement: null,
      getBoundingClientRect: () => ({ left: 0, right: 390, top: 80, bottom: 400 }),
    };
    s.style.overflowY = 'auto';
    expect(isObservationVisible(s.element)).toBe(false);
  });
  it('annule en quittant la vue, sans rejouer au retour', () => {
    const s = surface();
    highlightObservation(s.element);
    expect(s.value.dataset.updated).toBe('true');
    s.document.visibilityState = 'hidden';
    s.document.dispatchEvent(new Event('visibilitychange'));
    expect(s.value.dataset.updated).toBeUndefined();
    expect(s.animation.cancel).toHaveBeenCalledOnce();
    s.document.visibilityState = 'visible';
    s.document.dispatchEvent(new Event('visibilitychange'));
    expect(s.value.animate).toHaveBeenCalledOnce();
  });
  it('termine et nettoie l’effet, et respecte la réduction des mouvements', () => {
    const s = surface();
    highlightObservation(s.element);
    s.animation.onfinish?.();
    expect(s.value.dataset.updated).toBeUndefined();
    s.view.matchMedia = () => ({ matches: true });
    expect(highlightObservation(s.element)).toBeUndefined();
    expect(s.value.animate).toHaveBeenCalledOnce();
  });
});
