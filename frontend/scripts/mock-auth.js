export function mockAuth() {
  return {
    name: "local-mock-auth",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const requestPath = req.url?.split("?", 1)[0];
        if (req.method === "GET" && requestPath === "/api/auth/me") {
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.setHeader("Cache-Control", "no-store");
          res.end(JSON.stringify({ id: "mock-user", name: "本機測試住戶", role: "resident" }));
          return;
        }
        if (req.method === "GET" && requestPath === "/api/runtime-config.js") {
          res.setHeader("Content-Type", "application/javascript; charset=utf-8");
          res.setHeader("Cache-Control", "no-store");
          res.end('window.CommunityConfig = Object.freeze({ apiBaseUrl: "/api", lineLoginPath: "/auth/line/login", mockAuth: true });');
          return;
        }
        next();
      });
    },
  };
}
