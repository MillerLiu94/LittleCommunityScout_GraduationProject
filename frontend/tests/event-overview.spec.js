import { test, expect } from "@playwright/test";

const events = Array.from({ length: 12 }, (_, i) => ({
  id: i + 1, title: `社區事件 ${i + 1}`, type: i === 11 ? "道路" : "環境",
  status: i === 11 ? "resolved" : "pending", placeText: "臺北市", description: "事件描述",
}));

test.beforeEach(async ({ page }) => {
  await page.route("**/api/runtime-config.js", route => route.fulfill({ contentType: "application/javascript", body: 'window.CommunityConfig = { apiBaseUrl: "/api" };' }));
  await page.route(/\/api\/events\?.*/, route => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    return route.fulfill({ json: events.slice(offset, offset + 10) });
  });
});

test("篩選搜尋後續事件，並複製條件", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("pages/local-info/event-overview.html");
  await expect(page.getByRole("heading", { name: "社區事件 1", exact: true })).toBeVisible();
  await page.locator("#filter-keyword").fill("社區事件 12");
  await expect(page.getByRole("heading", { name: "社區事件 12", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "社區事件 1", exact: true })).toBeHidden();
  await page.locator("#filter-status").selectOption({ label: "已完成" });
  await page.locator("#filter-category").selectOption({ label: "道路" });
  await page.getByRole("button", { name: "複製篩選條件" }).click();
  await expect(page.locator("#filter-feedback")).toContainText("已複製");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("社區事件篩選條件：案件狀態：已完成；事件類別：道路；關鍵字：社區事件 12");
  await page.locator("#filter-keyword").fill("不存在的事件");
  await expect(page.locator("#filter-empty")).toBeVisible();
});

test("小助理可對話並於手機版操作", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.route("**/api/chat/stream", route => route.fulfill({ contentType: "text/event-stream", body: 'event: done\ndata: {"reply":"這是 AI 回覆"}\n\n' }));
  await page.goto("pages/local-info/event-overview.html");
  await page.getByRole("button", { name: "AI 小助理" }).click();
  await page.getByRole("textbox", { name: "輸入訊息" }).fill("幫我了解社區事件");
  await page.getByRole("button", { name: "送出訊息" }).click();
  await expect(page.getByText("這是 AI 回覆")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "關閉 AI 小助理" }).click();
  await expect(page.locator("#assistant-panel")).toBeHidden();
});

test("篩選載入失敗後可重試", async ({ page }) => {
  let failed = false;
  await page.route(/\/api\/events\?.*/, route => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    if (offset && !failed) { failed = true; return route.fulfill({ status: 500, body: "載入失敗" }); }
    return route.fulfill({ json: events.slice(offset, offset + 10) });
  });
  await page.goto("pages/local-info/event-overview.html");
  await expect(page.getByRole("heading", { name: "社區事件 1", exact: true })).toBeVisible();
  await page.locator("#filter-keyword").fill("社區事件 12");
  await expect(page.getByRole("button", { name: "重試載入" })).toBeVisible();
  await page.getByRole("button", { name: "重試載入" }).click();
  await expect(page.getByRole("heading", { name: "社區事件 12", exact: true })).toBeVisible();
});
