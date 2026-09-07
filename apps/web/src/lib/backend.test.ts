import { afterEach, describe, expect, it, vi } from "vitest";

import { BackendReadError, canReadPrevious, readBackend, requestBackend } from "./backend";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("bounded backend reads", () => {
  it("keeps HTTP failure categories so temporary failures are recoverable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 503 })));
    await expect(readBackend("/api/backend/api/v1/events")).rejects.toMatchObject({ status: 503 });
    expect(canReadPrevious({ data: { rows: [1] }, error: new BackendReadError(503) })).toBe(true);
    for (const status of [401, 403, 404]) {
      expect(canReadPrevious({ data: { rows: [1] }, error: new BackendReadError(status) })).toBe(
        false,
      );
    }
  });

  it("honours both caller cancellation and a request deadline", async () => {
    const controller = new AbortController();
    let received: AbortSignal | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_input, init: RequestInit) => {
        received = init.signal ?? null;
        return Promise.resolve(new Response("{}"));
      }),
    );
    const timeout = vi.spyOn(AbortSignal, "timeout");
    await requestBackend("/api/backend/api/v1/events", { signal: controller.signal });
    expect(timeout).toHaveBeenCalledWith(15_000);
    expect(received).not.toBe(controller.signal);
    controller.abort();
    expect((received as AbortSignal | null)?.aborted).toBe(true);
    timeout.mockRestore();
  });

  it("leaves mutation error bodies available and does not retry a write", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ code: "INVALID_STATE" }), { status: 409 }));
    vi.stubGlobal("fetch", fetch);
    const response = await requestBackend("/api/backend/api/v1/paper-bets", { method: "POST" });
    expect(await response.json()).toEqual({ code: "INVALID_STATE" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("rejects a hanging transport when its deadline actually expires", async () => {
    const nativeTimeout = AbortSignal.timeout.bind(AbortSignal);
    vi.spyOn(AbortSignal, "timeout").mockImplementation(() => nativeTimeout(5));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        (_input, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener(
              "abort",
              () => {
                reject(init.signal?.reason as DOMException);
              },
              {
                once: true,
              },
            );
          }),
      ),
    );
    await expect(requestBackend("/api/backend/api/v1/events")).rejects.toMatchObject({
      name: "TimeoutError",
    });
  });
});
