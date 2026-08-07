import { expect, test } from '@playwright/test';

test('生产应用外壳可以加载', async ({ page }) => {
  const response = await page.goto('/');

  expect(response).not.toBeNull();
  expect(response?.status()).toBeLessThan(500);
  await expect(page.locator('body')).toBeVisible();
  await expect(page.locator('body')).not.toBeEmpty();
});
