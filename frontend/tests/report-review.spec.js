import { expect, test } from "@playwright/test";

test.use({ isMobile: true, hasTouch: true, userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1" });

test("申報確認頁顯示欄位錯誤並可修正", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript(() => {
    sessionStorage.setItem("community-report-draft-v1", JSON.stringify({
      analysis: { category_id: 1, label: "路燈故障", description: "路燈故障需要協助維修處理" },
      uploadedPaths: ["photo.jpg"],
      location: { lat: 25.03, lng: 121.5, address: "臺北市" },
    }));
  });
  await page.goto("pages/report/report-review.html");
  await page.locator("#apply-description").click();
  await page.locator("#description-input").fill("太短");
  await page.locator("#apply-description").click();
  await expect(page.locator("#description-error")).toBeVisible();
  await expect(page.locator("#description-input")).toHaveAttribute("aria-invalid", "true");
  await page.locator("#description-input").fill("路燈持續閃爍需要協助維修處理");
  await page.locator("#apply-description").click();
  await expect(page.locator("#description-error")).toBeHidden();
  await expect(page.locator("#description-summary")).toHaveText("路燈持續閃爍需要協助維修處理");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

