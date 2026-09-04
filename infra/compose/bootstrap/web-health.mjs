/** Serveur de santé temporaire utilisé avant le ticket web dédié. */

import { createServer } from "node:http";

const server = createServer((request, response) => {
  if (request.url !== "/health") {
    response.writeHead(404).end();
    return;
  }

  response
    .writeHead(200, { "content-type": "application/json" })
    .end(JSON.stringify({ status: "ok", phase: "bootstrap" }));
});

server.listen(3000, "0.0.0.0");

for (const event of ["SIGINT", "SIGTERM"]) {
  process.once(event, () => server.close(() => process.exit(0)));
}
