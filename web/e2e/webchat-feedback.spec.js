import { expect, test } from '@playwright/test';
import path from 'node:path';

for (const width of [1919, 320]) {
  test(`右侧助手反馈弹窗居中并显示当前评分（${width}px）`, async ({ page }) => {
    const height = width === 320 ? 600 : 933;
    await page.setViewportSize({ width, height });
    await page.route('**/webchat-feedback-test', route => route.fulfill({
      contentType: 'text/html; charset=utf-8',
      body: '<meta name="viewport" content="width=device-width,initial-scale=1"><main id="webchat-root" style="position:fixed;inset:0 0 0 auto;width:min(378px,100vw)"></main>',
    }));

    const openConversation = async () => {
      await page.goto('/webchat-feedback-test');
      await page.addStyleTag({ path: path.resolve('node_modules/tailwindcss/preflight.css') });
      await page.addStyleTag({ url: '/webchat/style.css' });
      await page.addScriptTag({ url: '/webchat/webchat.js' });
      await page.evaluate(() => {
        window.WebChat.default({
          sessionId: 'feedback-test',
          initialMessages: [{
            id: 'answer', persistedMessageId: 1, sender: 'bot', type: 'text',
            content: '测试回答', timestamp: 1, feedback: sessionStorage.getItem('vote'),
          }],
          onAnswerFeedback: async (_id, vote) => {
            if (vote) sessionStorage.setItem('vote', vote);
            else sessionStorage.removeItem('vote');
          },
        }, 'webchat-root');
      });
    };

    await openConversation();
    const rating = page.getByRole('button', { name: '评价回复' });
    const thumb = rating.locator('path').first();
    await expect(thumb).toHaveCSS('fill', 'none');

    for (const [label, other] of [['回复优秀', '回复不佳'], ['回复不佳', '回复优秀']]) {
      await rating.click();
      const option = page.getByRole('menuitemradio', { name: label });
      await option.click();
      const dialog = page.getByRole('dialog', { name: '提交反馈' });
      await expect(dialog).toBeVisible();
      const box = await dialog.boundingBox();
      expect(box.width).toBeLessThanOrEqual(width - 32);
      expect(Math.abs(box.x + box.width / 2 - width / 2)).toBeLessThan(1);
      expect(Math.abs(box.y + box.height / 2 - height / 2)).toBeLessThan(1);
      await dialog.getByRole('button', { name: '关闭' }).click();
      await expect(thumb).toHaveCSS('fill', await thumb.evaluate(el => getComputedStyle(el).color));

      await openConversation();
      await expect(thumb).toHaveCSS('fill', await thumb.evaluate(el => getComputedStyle(el).color));
      await rating.click();
      const selected = option.locator('path');
      await expect(option).toHaveAttribute('aria-checked', 'true');
      await expect(selected).toHaveCSS('fill', await selected.evaluate(el => getComputedStyle(el).color));
      await expect(page.getByRole('menuitemradio', { name: other }).locator('path')).toHaveCSS('fill', 'none');
      await option.press('Escape');
    }
    await rating.click();
    await page.getByRole('menuitemradio', { name: '回复不佳' }).click();
    await expect(thumb).toHaveCSS('fill', 'none');
  });
}
