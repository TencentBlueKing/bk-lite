import { expect, test } from '@playwright/test';

test('首次进入 OpsPilot 时引导气泡位于视口内', async ({ page }) => {
  await page.goto('/');

  const mask = page.locator('.ant-tour-mask');
  const popup = page.locator('.ant-tour');

  await expect(mask).toBeVisible();
  await expect(popup).toContainText('第一步: 接入LLM大模型');

  const popupRect = await popup.boundingBox();
  const viewport = page.viewportSize();

  expect(popupRect).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(popupRect!.x).toBeGreaterThanOrEqual(0);
  expect(popupRect!.y).toBeGreaterThanOrEqual(0);
  expect(popupRect!.x).toBeLessThan(viewport!.width);
  expect(popupRect!.y).toBeLessThan(viewport!.height);
});
