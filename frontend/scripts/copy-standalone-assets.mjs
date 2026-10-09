// Runs after `next build`. The standalone server (.next/standalone/server.js) does not include the static assets,
// so copy them next to it; `npm start` and the Docker image then serve the same build.
import { cpSync, existsSync } from "node:fs";

const standalone = ".next/standalone";

if (existsSync(standalone)) {
  cpSync(".next/static", `${standalone}/.next/static`, { recursive: true });
  if (existsSync("public")) cpSync("public", `${standalone}/public`, { recursive: true });
}
