import { test, expect } from "@playwright/test";

const cases = Array.from({ length: 12 }, (_, i) => ({
  title: `申報事件 ${i + 1}`, category: i === 11 ? "道路" : "環境", status: i === 11 ? "resolved" : "pending", address: "臺北市", description: "事件描述",
}));

test.beforeEach(async ({ page }) => {
  await page.route("**/api/runtime-config.js", route => route.fulfill({ contentType: "application/javascript", body: 'window.CommunityConfig = { apiBaseUrl: "/api" };' }));
  await page.route("**/api/auth/me", route => route.fulfill({ json: { id: 1 } }));
  await page.route(/\/api\/cases\?.*/, route => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get("offset"));
    return route.fulfill({ json: { cases: cases.slice(offset, offset + 10), hasMore: offset + 10 < cases.length } });
  });
});

test("申報狀態使用統一文字並處理後端標籤", async ({ page }) => {
  await page.route(/\/api\/cases\?.*/, route => route.fulfill({ json: { cases: [
    { title: "未處理申報", status: "pending", status_label: "待處理" },
    { title: "處理中申報", status: "in-progress" },
    { title: "已結案申報", status_label: "已完成" },
    { title: "未知申報", status: "unexpected", status_label: "其他" },
  ], hasMore: false } }));
  await page.goto("pages/local-info/my-reports.html");
  await expect(page.locator(".case-status")).toHaveText(["未處理", "處理中", "已結案", "狀態未提供"]);
  await expect(page.locator("#filter-status option")).toHaveText(["全部狀態", "未處理", "處理中", "已結案"]);
});

test("篩選會搜尋後續紀錄並可複製條件", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("pages/local-info/my-reports.html");
  await expect(page.getByRole("heading", { name: "申報事件 1", exact: true })).toBeVisible();
  await page.locator("#filter-keyword").fill("申報事件 12");
  await expect(page.getByRole("heading", { name: "申報事件 12", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "申報事件 1", exact: true })).toBeHidden();
  await page.locator("#filter-status").selectOption({ label: "已結案" });
  await page.locator("#filter-category").selectOption({ label: "道路" });
  await page.getByRole("button", { name: "複製篩選條件" }).click();
  await expect(page.locator("#filter-feedback")).toContainText("已複製");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("案件狀態：已結案；事件類別：道路；關鍵字：申報事件 12");
  await page.locator("#filter-keyword").fill("不存在的案件");
  await expect(page.locator("#filter-empty")).toBeVisible();
});

test("小助理在頁面內沿用 AI 對話並可關閉", async ({ page }) => {
  let request;
  await page.route("**/api/chat/stream", async route => {
    request = route.request().postDataJSON();
    await route.fulfill({ contentType: "text/event-stream", body: 'event: done\ndata: {"reply":"這是 AI 回覆"}\n\n' });
  });
  await page.goto("pages/local-info/my-reports.html");
  await page.getByRole("button", { name: "AI 小助理" }).click();
  await page.getByRole("textbox", { name: "輸入訊息" }).fill("幫我了解申報進度");
  await page.getByRole("button", { name: "送出訊息" }).click();
  await expect(page.getByText("這是 AI 回覆")).toBeVisible();
  expect(request.message).toBe("幫我了解申報進度");
  await page.getByRole("button", { name: "關閉 AI 小助理" }).click();
  await expect(page.locator("#assistant-panel")).toBeHidden();
  await page.getByRole("button", { name: "AI 小助理" }).click();
  await expect(page.getByText("這是 AI 回覆")).toBeVisible();
});

test("手機版篩選與對話視窗可操作", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("pages/local-info/my-reports.html");
  await page.getByRole("button", { name: "AI 小助理" }).click();
  await expect(page.getByRole("textbox", { name: "輸入訊息" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
