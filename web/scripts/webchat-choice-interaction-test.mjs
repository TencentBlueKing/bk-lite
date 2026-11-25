import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const asset = await readFile(new URL('../public/webchat/webchat.js', import.meta.url));
const stylesheet = await readFile(new URL('../public/webchat/style.css', import.meta.url));
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const requests = [];
  const events = [
    { type: 'RUN_STARTED' },
    { type: 'CUSTOM', name: 'user_choice_request', value: {
      choice_id: 'repeat', title: '再次确认？', options: ['确认执行', '取消'],
    } },
    { type: 'RUN_FINISHED' },
  ];
  let fail = false;
  await context.route('http://choice.test/**', async route => {
    if (route.request().url().endsWith('/style.css')) {
      return route.fulfill({ contentType: 'text/css', body: stylesheet });
    }
    if (route.request().url().endsWith('/webchat.js')) {
      return route.fulfill({ contentType: 'application/javascript; charset=utf-8', body: asset });
    }
    if (route.request().method() === 'POST') {
      requests.push(route.request().postDataJSON());
      return route.fulfill({ status: fail ? 503 : 200, contentType: 'text/event-stream',
        body: events.map(event => 'data: ' + JSON.stringify(event) + '\n\n').join('') });
    }
    return route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<meta charset=utf-8><link rel="stylesheet" href="/style.css"><div id="webchat-root"></div><script src="/webchat.js"></script>' });
  });
  const card = (id, title) => ({
    choice_id: id, title, options: ['确认执行', '取消'].map(label => ({ key: label, label })),
    min_select: 1, max_select: 1, display_hint: 'auto', status: 'pending', received_at: Date.now(), timeout_seconds: 0,
  });
  const messages = [
    { id: 'prior', sender: 'bot', content: '', metadata: { userChoiceRequests: [card('old', '上一个问题')] } },
    { id: 'question', sender: 'user', content: '检查时间服务' },
    { id: 'server-rehydrated-id', sender: 'bot', content: '', metadata: { userChoiceRequests: [
      card('superseded', '已经替换的问题'), card('current', '执行当前脚本？\n  echo fixture'),
    ] } },
  ];
  async function openChat(tab, history) {
    await tab.goto('http://choice.test/');
    await tab.evaluate(initialMessages => window.WebChat.default({
      initialMessages, sseUrl: '/chat', enableStorage: false, customData: { session_id: 'fixture' },
    }, 'webchat-root'), history);
  }
  const secondTab = await context.newPage();
  await openChat(page, messages);
  await openChat(secondTab, [
    { ...messages[2], metadata: { userChoiceRequests: [card('other-tab', '另一页的脚本？')] } },
  ]);
  const title = page.getByText('执行当前脚本？ echo fixture', { exact: true });
  await title.waitFor();
  assert.equal(await title.evaluate(node => getComputedStyle(node).whiteSpace), 'pre-wrap');
  const action = (name) => page.getByRole('button', { name, exact: true }).and(page.locator('button:enabled'));
  const confirm = action('确认执行');
  assert.equal(await confirm.count(), 1, 'Only the current pending question exposes actions');
  fail = true;
  await confirm.click();
  await page.getByText(/503/).first().waitFor();
  assert.equal(await action('取消').count(), 1, 'A rejected HTTP request leaves the question pending');
  fail = false;
  await confirm.click();
  await page.getByText('再次确认？', { exact: true }).waitFor();
  assert.equal(requests[1].message, '确认执行');
  assert.equal(requests[1].choice_id, 'current');
  assert.equal(requests[1].choice_option, '确认执行');
  assert.equal(requests[1].reply_to_choice_id, undefined);
  async function sendAndInspect(tab, send) {
    const [request] = await Promise.all([tab.waitForRequest(req => req.method() === 'POST'), send()]);
    return request.postDataJSON();
  }
  const cancel = await sendAndInspect(page, () => action('取消').click());
  assert.equal(cancel.choice_id, 'repeat');
  assert.equal(cancel.message, '取消');
  async function reply(tab, text) {
    const input = tab.getByRole('textbox').last();
    await input.fill(text);
    return sendAndInspect(tab, () => input.press('Enter'));
  }
  const typed = await reply(secondTab, '一');
  assert.equal(typed.reply_to_choice_id, 'other-tab');
  assert.equal(typed.message, '一');
  assert.equal(typed.choice_option, undefined);
  assert.equal(typed.choice_id, undefined);
  const inline = secondTab.locator('[data-a2ui-event="user_choice_request"] input').last();
  await inline.fill('二');
  const inlineAnswer = await sendAndInspect(secondTab, () => inline.press('Enter'));
  assert.equal(inlineAnswer.reply_to_choice_id, 'repeat');
  assert.equal(inlineAnswer.message, '二');
  assert.equal(inlineAnswer.choice_option, undefined);
  const replayTab = await context.newPage();
  await openChat(replayTab, [
    { id: 'previous-answer', sender: 'user', content: '一' },
    { ...messages[2], metadata: { userChoiceRequests: [card('new-script', '变更后的脚本？')] } },
  ]);
  await replayTab.getByText('变更后的脚本？', { exact: true }).hover();
  const regenerated = await sendAndInspect(replayTab, () => replayTab.getByTitle('重新生成', { exact: true }).last().click());
  assert.equal(regenerated.message, '一');
  assert.equal(regenerated.reply_to_choice_id, '');
  assert.equal(regenerated.choice_option, undefined);
  assert.equal(regenerated.choice_id, undefined);
  const plainTab = await context.newPage();
  await openChat(plainTab, [{ ...messages[2], metadata: { userChoiceRequests: [card('history-generated', '历史文字卡')] } }]);
  await plainTab.getByText('历史文字卡', { exact: true }).waitFor();
  assert.equal(await plainTab.getByRole('button', { name: '确认执行', exact: true }).count(), 0);
  const plain = await reply(plainTab, '聊点别的');
  assert.equal(plain.reply_to_choice_id, '');
  assert.equal(plain.message, '聊点别的');
} finally {
  await browser.close();
}
