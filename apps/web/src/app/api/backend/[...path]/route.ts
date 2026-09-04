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

export async function GET(request: Request, context: ProxyRouteContext) {
  const { path } = await context.params;
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const upstreamUrl = new URL(encodedPath, `${apiBaseUrl().replace(/\/$/, "")}/`);
  upstreamUrl.search = new URL(request.url).search;

  try {
    const upstreamResponse = await fetch(upstreamUrl, {
      cache: "no-store",
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MILLISECONDS),
    });
    const contentType = upstreamResponse.headers.get("content-type");
    const headers = new Headers({ "cache-control": "no-store" });
    if (contentType) {
      headers.set("content-type", contentType);
    }

    return new Response(upstreamResponse.body, {
      headers,
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
    });
  } catch {
    return problemResponse();
  }
}
