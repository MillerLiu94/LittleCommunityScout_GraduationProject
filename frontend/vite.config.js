import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const siteRoot = path.resolve(frontendRoot, "..");
const projectDirectory = path.basename(frontendRoot);

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, frontendRoot, "");
  const configuredApi = env.API_BASE_URL;
  if (!configuredApi) throw new Error("Set API_BASE_URL in .env.");

  const apiUrl = new URL(configuredApi);
  if (!/^https?:$/.test(apiUrl.protocol)) {
    throw new Error("API_BASE_URL must use http or https.");
  }
  if (apiUrl.pathname !== "/" && !/^\/api\/?$/i.test(apiUrl.pathname)) {
    throw new Error("API_BASE_URL must be the backend origin, optionally ending in /api.");
  }

  return {
    root: siteRoot,
    envDir: frontendRoot,
    plugins: [
      {
        name: "frontend-root-redirect",
        configureServer(server) {
          server.middlewares.use((req, res, next) => {
            const requestPath = req.url?.split("?", 1)[0];
            const query = req.url?.includes("?") ? req.url.slice(req.url.indexOf("?")) : "";
            if (requestPath === "/") {
              res.statusCode = 302;
              res.setHeader("Location", `/${projectDirectory}/index.html` + query);
              res.end();
              return;
            }
            next();
          });
        },
      },
    ],
    server: {
      host: "0.0.0.0",
      port: 5500,
      strictPort: true,
      open: `/${projectDirectory}/index.html`,
      allowedHosts: env.DEV_TUNNEL_HOST ? [env.DEV_TUNNEL_HOST] : [],
      hmr: false,
      proxy: {
        "/api": {
          target: apiUrl.origin,
          changeOrigin: true,
          secure: true,
        },
        "/uploads": {
          target: apiUrl.origin,
          changeOrigin: true,
          secure: true,
        },
      },
    },
  };
});
