const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const UPSTREAM_TIMEOUT_MILLISECONDS = 10_000;
const MAX_BODY_BYTES = 65_536;

type ProxyRouteContext = Readonly<{
  params: Promise<Readonly<{ path: string[] }>>;
}>;

function apiBaseUrl() {
  return process.env.API_BASE_URL?.trim() ?? DEFAULT_API_BASE_URL;
}

function problemResponse() {
  return Response.json(
    {
      code: "DEPENDENCY_UNAVAILABLE",
      detail: "Le service de données ne répond pas. Réessayez dans quelques instants.",
      instance: "/api/backend",
      status: 503,
      title: "Service de données indisponible",
      type: "about:blank",
    },
    {
      headers: { "cache-control": "no-store" },
      status: 503,
    },
  );
}

async function forward(request: Request, context: ProxyRouteContext) {
  const { path } = await context.params;
  if (path[0] !== "api" || path[1] !== "v1" || path.some((part) => part === "." || part === "..")) {
    return Response.json({ code: "INVALID_PATH", status: 400 }, { status: 400 });
  }
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const upstreamUrl = new URL(encodedPath, `${apiBaseUrl().replace(/\/$/, "")}/`);
  upstreamUrl.search = new URL(request.url).search;

  try {
    const headers = new Headers({ accept: "application/json" });
    const contentType = request.headers.get("content-type");
    const idempotencyKey = request.headers.get("idempotency-key");
    if (contentType) headers.set("content-type", contentType);
    if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
    for (const name of ["origin", "x-metiquo-csrf", "sec-fetch-site"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    const cookies = request.headers
      .get("cookie")
      ?.split(";")
      .filter((cookie) =>
        ["metiquo_owner", "__Host-metiquo_owner"].includes(cookie.trim().split("=")[0] ?? ""),
      )
      .join(";");
    if (cookies) headers.set("cookie", cookies);
    const chunks: Uint8Array[] = [];
    let bodySize = 0;
    if (request.method !== "GET" && request.body) {
      const reader = request.body.getReader();
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          bodySize += value.length;
          if (bodySize > MAX_BODY_BYTES) {
            await reader.cancel();
            return Response.json({ code: "INPUT_TOO_LARGE", status: 413 }, { status: 413 });
          }
          chunks.push(value);
        }
      } finally {
        reader.releaseLock();
      }
    }
    const body = Buffer.concat(chunks, bodySize);
    const upstreamResponse = await fetch(upstreamUrl, {
      ...(body.length > 0 ? { body } : {}),
      cache: "no-store",
      headers,
      method: request.method,
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MILLISECONDS),
    });
    const responseContentType = upstreamResponse.headers.get("content-type");
    const responseHeaders = new Headers({ "cache-control": "no-store" });
    if (responseContentType) {
      responseHeaders.set("content-type", responseContentType);
    }
    for (const cookie of upstreamResponse.headers.getSetCookie()) {
      responseHeaders.append("set-cookie", cookie);
    }
    const trace = upstreamResponse.headers.get("x-trace-id");
    if (trace) responseHeaders.set("x-trace-id", trace);
    const retryAfter = upstreamResponse.headers.get("retry-after");
    if (retryAfter) responseHeaders.set("retry-after", retryAfter);

    return new Response(upstreamResponse.body, {
      headers: responseHeaders,
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
    });
  } catch {
    return problemResponse();
  }
}

export async function GET(request: Request, context: ProxyRouteContext) {
  return forward(request, context);
}

export async function POST(request: Request, context: ProxyRouteContext) {
  return forward(request, context);
}
