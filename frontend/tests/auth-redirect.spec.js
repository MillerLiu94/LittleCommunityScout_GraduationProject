import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/runtime-config.js", route => route.fulfill({ contentType: "application/javascript", body: 'window.CommunityConfig = { apiBaseUrl: "/api" };' }));
  await page.route("**/api/auth/me", route => route.fulfill({ status: 401, json: { detail: "登入已過期" } }));
});

test("未登入瀏覽首頁時導向登入頁", async ({ page }) => {
  await page.goto("index.html");
  await expect(page).toHaveURL(/\/pages\/login\/login\.html$/);
});

test("未登入瀏覽受保護頁面時導向登入頁，登入後返回原頁", async ({ page }) => {
  await page.goto("pages/local-info/my-reports.html?view=all#reports-list");
  await expect(page).toHaveURL(/\/pages\/login\/login\.html$/);
  await page.route("**/api/auth/me", route => route.fulfill({ json: { id: 1 } }));
  await page.route(/\/api\/cases\?.*/, route => route.fulfill({ json: [] }));
  await page.reload();
  await expect(page).toHaveURL(/\/pages\/local-info\/my-reports\.html\?view=all#reports-list$/);
});

test("受保護 API 回傳 401 時導向登入頁", async ({ page }) => {
  let expired = false;
  await page.route("**/api/auth/me", route => route.fulfill(expired ? { status: 401, json: { detail: "登入已過期" } } : { json: { id: 1 } }));
  await page.route(/\/api\/cases\?.*/, route => {
    expired = true;
    return route.fulfill({ status: 401, json: { detail: "登入已過期" } });
  });
  await page.goto("pages/local-info/my-reports.html");
  await expect(page).toHaveURL(/\/pages\/login\/login\.html$/);
});
