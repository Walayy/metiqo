const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const UPSTREAM_TIMEOUT_MILLISECONDS = 10_000;

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
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const upstreamUrl = new URL(encodedPath, `${apiBaseUrl().replace(/\/$/, "")}/`);
  upstreamUrl.search = new URL(request.url).search;

  try {
    const headers = new Headers({ accept: "application/json" });
    const contentType = request.headers.get("content-type");
    const idempotencyKey = request.headers.get("idempotency-key");
    if (contentType) headers.set("content-type", contentType);
    if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
    const body = request.method === "GET" ? "" : await request.text();
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
