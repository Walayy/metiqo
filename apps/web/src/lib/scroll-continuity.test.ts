import { describe, expect, it } from 'vitest';
import { createScrollContinuity } from './scroll-continuity';

function reader() {
  const state = { content: 1600, viewport: 600, top: 900, extra: 0, reduced: false };
  let id = 0;
  const frames = new Map<number, FrameRequestCallback>();
  const height = () => Math.max(state.viewport, state.content + state.extra);
  const controller = createScrollContinuity(
    {
      read: () => ({ top: state.top, height: height(), viewport: state.viewport }),
      reserve: (pixels) => {
        state.extra = pixels;
        state.top = Math.min(state.top, height() - state.viewport);
      },
      scroll: (top) => {
        state.top = Math.max(0, Math.min(top, height() - state.viewport));
      },
      reducedMotion: () => state.reduced,
    },
    {
      request: (callback) => {
        frames.set(++id, callback);
        return id;
      },
      cancel: (key) => {
        frames.delete(key);
      },
    },
  );
  const tick = (time: number) => {
    const callbacks = [...frames.values()];
    frames.clear();
    callbacks.forEach((callback) => callback(time));
  };
  const shrink = (content: number) => {
    state.content = content;
    state.top = Math.min(state.top, height() - state.viewport);
    controller.check();
  };
  return { state, controller, tick, shrink, frames };
}

describe('continuité des zones défilantes', () => {
  it('conserve une position encore valide, sans animation ni espace ajouté', () => {
    const r = reader();
    r.state.top = 200;
    r.controller.scroll();
    r.shrink(1000);
    expect(r.state.top).toBe(200);
    expect(r.state.extra).toBe(0);
    expect(r.frames.size).toBe(0);
  });

  it('restaure le point de lecture avant de rejoindre progressivement la nouvelle fin', () => {
    const r = reader();
    r.shrink(900);
    expect(r.state.top).toBe(900);
    r.tick(0);
    r.tick(100);
    expect(r.state.top).toBeGreaterThan(300);
    expect(r.state.top).toBeLessThan(900);
    r.tick(600);
    expect(r.state.top).toBe(300);
    expect(r.state.extra).toBe(0);
    expect(r.frames.size).toBe(0);
  });

  it('gère aussi la disparition complète de la scrollbar', () => {
    const r = reader();
    r.shrink(100);
    expect(r.state.top).toBe(900);
    r.tick(0);
    r.tick(140);
    expect(r.state.top).toBeGreaterThan(0);
    r.tick(600);
    expect(r.state.top).toBe(0);
    expect(r.state.extra).toBe(0);
  });

  it('abandonne la compensation quand un changement rapide redonne assez de contenu', () => {
    const r = reader();
    r.shrink(900);
    r.tick(0);
    r.tick(80);
    const top = r.state.top;
    r.state.content = 1800;
    r.controller.check();
    expect(r.state.top).toBe(top);
    expect(r.state.extra).toBe(0);
    expect(r.frames.size).toBe(0);
  });

  it('laisse la main au lecteur puis reprend depuis sa nouvelle position', () => {
    const r = reader();
    r.shrink(900);
    r.controller.pause();
    expect(r.frames.size).toBe(0);
    r.state.top = 500;
    r.controller.scroll();
    r.controller.resume();
    expect(r.state.top).toBe(500);
    r.tick(0);
    r.tick(600);
    expect(r.state.top).toBe(300);
  });

  it('respecte les mouvements réduits et nettoie les réserves au démontage', () => {
    const r = reader();
    r.state.reduced = true;
    r.shrink(900);
    expect(r.state.top).toBe(300);
    expect(r.frames.size).toBe(0);
    expect(r.state.extra).toBe(0);
    const s = reader();
    s.shrink(900);
    s.controller.dispose();
    expect(s.frames.size).toBe(0);
    expect(s.state.extra).toBe(0);
  });
});
