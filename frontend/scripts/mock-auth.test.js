import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer as createHttpServer } from "node:http";
import { createServer } from "vite";

test("mock mode only substitutes the local identity and runtime config", async () => {
  const backend = createHttpServer((req, res) => {
    res.writeHead(401, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ upstream: true, path: req.url }));
  });
  await new Promise(resolve => backend.listen(0, "127.0.0.1", resolve));
  const previousApi = process.env.API_BASE_URL;
  process.env.API_BASE_URL = `http://127.0.0.1:${backend.address().port}`;
  let server;
  try {
    server = await createServer({ mode: "mock", server: { port: 0, strictPort: false, open: false } });
    await server.listen();
    const base = `http://127.0.0.1:${server.httpServer.address().port}`;
    const user = await fetch(`${base}/api/auth/me`);
    assert.equal((await user.json()).id, "mock-user");
    assert.match(await (await fetch(`${base}/api/runtime-config.js`)).text(), /mockAuth: true/);
    const cases = await fetch(`${base}/api/cases`);
    assert.equal(cases.status, 401);
    assert.equal((await cases.json()).upstream, true);
    assert.equal((await fetch(`${base}/api/auth/me`, { method: "POST" })).status, 401);
  } finally {
    await server?.close();
    await new Promise(resolve => backend.close(resolve));
    if (previousApi === undefined) delete process.env.API_BASE_URL;
    else process.env.API_BASE_URL = previousApi;
  }
});

test("normal mode continues to use the backend for identity", async () => {
  const backend = createHttpServer((req, res) => { res.writeHead(401); res.end(); });
  await new Promise(resolve => backend.listen(0, "127.0.0.1", resolve));
  const previousApi = process.env.API_BASE_URL;
  process.env.API_BASE_URL = `http://127.0.0.1:${backend.address().port}`;
  let server;
  try {
    server = await createServer({ mode: "development", server: { host: "127.0.0.1", port: 0, strictPort: false, open: false } });
    await server.listen();
    const response = await fetch(`http://127.0.0.1:${server.httpServer.address().port}/api/auth/me`);
    assert.equal(response.status, 401);
  } finally {
    await server?.close();
    await new Promise(resolve => backend.close(resolve));
    if (previousApi === undefined) delete process.env.API_BASE_URL;
    else process.env.API_BASE_URL = previousApi;
  }
});
