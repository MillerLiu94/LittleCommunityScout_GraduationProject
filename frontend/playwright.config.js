import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDirectory = path.basename(path.dirname(fileURLToPath(import.meta.url)));
const baseURL = `http://127.0.0.1:5500/${projectDirectory}/`;

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL,
    browserName: "chromium",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1",
    url: `${baseURL}index.html`,
    reuseExistingServer: !process.env.CI,
  },
});
