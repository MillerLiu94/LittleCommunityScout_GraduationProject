import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/runtime-config.js", route => route.fulfill({
    contentType: "application/javascript",
    body: 'window.CommunityConfig = { apiBaseUrl: "/api", lineLoginPath: "/auth/line/login" };',
  }));
});

test("測試人員不需 LINE 即可進入首頁，受保護 API 拒絕時不循環跳頁", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ status: 401, json: { detail: "未登入" } }));
  await page.route(/\/api\/cases\?.*/, route => route.fulfill({ status: 401, json: { detail: "未登入" } }));
  await page.goto("pages/login/login.html");
  await page.getByRole("button", { name: "測試人員登入" }).click();
  await expect(page).toHaveURL(/\/index\.html$/);
  await page.reload();
  await expect(page).toHaveURL(/\/index\.html$/);
  await page.goto("pages/local-info/my-reports.html");
  await expect(page.locator("#report-status")).toContainText("測試人員沒有後端登入狀態");
  await expect(page).toHaveURL(/\/pages\/local-info\/my-reports\.html$/);
});

test("正式登入時身分與案件權限不一致，不應循環跳頁", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill({ json: { id: "user" } }));
  await page.route(/\/api\/cases\?.*/, route => route.fulfill({ status: 401, json: { detail: "登入已過期" } }));
  await page.goto("pages/local-info/my-reports.html");
  await expect(page).toHaveURL(/\/pages\/login\/login\.html$/);
  await expect(page.locator("#login-status")).toContainText("請重新登入");
  await page.reload();
  await expect(page.locator("#login-status")).toContainText("請重新登入");
  await page.route(/\/api\/cases\?.*/, route => route.fulfill({ json: [] }));
  await page.goto("pages/login/login.html?login=success");
  await expect(page).toHaveURL(/\/pages\/local-info\/my-reports\.html$/);
});
