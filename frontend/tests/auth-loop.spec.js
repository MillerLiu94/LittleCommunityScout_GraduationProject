import { test, expect } from "@playwright/test";

async function setup(page, mockAuth) {
  await page.route("**/api/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: `window.CommunityConfig = { apiBaseUrl: "/api", mockAuth: ${mockAuth} };`,
  }));
  await page.route("**/api/auth/me", route => route.fulfill({ json: { id: "user" } }));
  await page.route(/\/api\/cases\?.*/, route => route.fulfill({ status: 401, json: { detail: "登入已過期" } }));
}

test("模擬登入時後端拒絕案件查詢，不應循環跳頁", async ({ page }) => {
  await setup(page, true);
  await page.goto("pages/local-info/my-reports.html");
  await expect(page.locator("#report-status")).toContainText("模擬使用者");
  await expect(page).toHaveURL(/\/pages\/local-info\/my-reports\.html$/);
});

test("正式登入時身分與案件權限不一致，不應循環跳頁", async ({ page }) => {
  await setup(page, false);
  await page.goto("pages/local-info/my-reports.html");
  await expect(page).toHaveURL(/\/pages\/login\/login\.html$/);
  await expect(page.locator("#login-status")).toContainText("請重新登入");
  await expect(page.getByRole("button", { name: "使用通訊軟體登入" })).toBeVisible();
  await page.reload();
  await expect(page.locator("#login-status")).toContainText("請重新登入");
  await page.route(/\/api\/cases\?.*/, route => route.fulfill({ json: [] }));
  await page.goto("pages/login/login.html?login=success");
  await expect(page).toHaveURL(/\/pages\/local-info\/my-reports\.html$/);
});

test("申報頁與登入頁的身分檢查結果不一致，不應循環跳頁", async ({ page }) => {
  await page.route("**/api/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: 'window.CommunityConfig = { apiBaseUrl: "/api", mockAuth: true };',
  }));
  await page.route("**/api/auth/me", route => route.fulfill(
    route.request().frame().url().includes("my-reports.html")
      ? { status: 401, json: { detail: "登入已過期" } }
      : { json: { id: "mock-user" } }
  ));
  await page.goto("pages/local-info/my-reports.html");
  await expect(page.locator("#login-status")).toContainText("請重新登入");
  await expect(page).toHaveURL(/\/pages\/login\/login\.html$/);
  await page.reload();
  await expect(page.locator("#login-status")).toContainText("請重新登入");
});
