/**
 * webchat i18n 回归测试
 *
 * 范围：只覆盖前端写死的文案。后端返回的数据（会话标题、消息正文、错误原文）一律原样展示，
 * 不做翻译，也不应被这套词条影响。
 *
 * 1. zh/en 两份内置词条的 key 集合必须一致（漏一侧会在切换语言时露出 key 本身）。
 * 2. 占位符在两侧必须一致，否则英文界面会丢变量。
 * 3. 组件源码里不再有面向用户的中文展示串（t()/translate() 的中文兜底、*_FALLBACK 映射表除外）。
 * 4. 显式传 locale='en' 时组件输出英文；不传时保持中文。
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { buildSync } from 'esbuild';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const coreSrc = path.join(rootDir, 'packages/webchat-core/src');
const uiSrc = path.join(rootDir, 'packages/webchat-ui/src');
const outDir = path.join(rootDir, '.test-dist', 'i18n');
fs.mkdirSync(outDir, { recursive: true });
process.on('exit', () => {
  fs.rmSync(outDir, { recursive: true, force: true });
});

/** 剥掉行注释与块注释，逐行返回纯代码。源码可能是 CRLF，必须先去掉 \r。 */
const stripComments = (text) => {
  const out = [];
  let inBlock = false;
  for (const raw of text.split('\n')) {
    let code = raw.replace(/\r$/, '');
    if (inBlock) {
      const end = code.indexOf('*/');
      if (end === -1) {
        out.push('');
        continue;
      }
      code = code.slice(end + 2);
      inBlock = false;
    }
    const start = code.indexOf('/*');
    if (start !== -1) {
      const tail = code.indexOf('*/', start);
      if (tail === -1) {
        code = code.slice(0, start);
        inBlock = true;
      } else {
        code = code.slice(0, start) + code.slice(tail + 2);
      }
    }
    out.push(code.replace(/\/\/.*$/, ''));
  }
  return out;
};

const buildCoreI18n = async () => {
  const outfile = path.join(outDir, 'i18n.mjs');
  buildSync({
    entryPoints: [path.join(coreSrc, 'i18n.ts')],
    bundle: true,
    platform: 'node',
    format: 'esm',
    outfile,
  });
  return import(pathToFileURL(outfile));
};

test('zh and en catalogs expose the same keys', async () => {
  const { webChatCatalogs } = await buildCoreI18n();
  const zhKeys = Object.keys(webChatCatalogs.zh).sort();
  const enKeys = Object.keys(webChatCatalogs.en).sort();
  assert.ok(zhKeys.length > 0);
  assert.deepEqual(enKeys, zhKeys);
});

test('every key keeps identical placeholders on both sides', async () => {
  const { webChatCatalogs } = await buildCoreI18n();
  const placeholders = (value) => (value.match(/\{\w+\}/g) ?? []).sort();
  for (const [key, zhValue] of Object.entries(webChatCatalogs.zh)) {
    assert.deepEqual(
      placeholders(webChatCatalogs.en[key]),
      placeholders(zhValue),
      `placeholder mismatch for ${key}`,
    );
  }
});

test('translator falls back to the key, then to the supplied default', async () => {
  const { createTranslator } = await buildCoreI18n();
  const t = createTranslator('en');
  assert.equal(t('does.not.exist'), 'does.not.exist');
  assert.equal(t('does.not.exist', '兜底'), '兜底');
});

test('translator interpolates values and keeps the raw placeholder when absent', async () => {
  const { createTranslator } = await buildCoreI18n();
  const t = createTranslator('en');
  assert.equal(t('session.daysAgo', '{count} 天前', { count: 3 }), '3 d ago');
  assert.equal(t('session.daysAgo', '{count} 天前'), '{count} d ago');
});

test('normalizeLocale only accepts english variants', async () => {
  const { normalizeLocale } = await buildCoreI18n();
  assert.equal(normalizeLocale('en'), 'en');
  assert.equal(normalizeLocale('en-US'), 'en');
  assert.equal(normalizeLocale('zh'), 'zh');
  assert.equal(normalizeLocale('zh-Hans'), 'zh');
  assert.equal(normalizeLocale(undefined), 'zh');
});

test('setWebChatLocale switches the module-level translator', async () => {
  const { setWebChatLocale, translate, getWebChatLocale } = await buildCoreI18n();
  assert.equal(getWebChatLocale(), 'zh');
  assert.equal(setWebChatLocale('en'), 'en');
  assert.equal(translate('session.new'), 'New conversation');
  setWebChatLocale('zh');
  assert.equal(translate('session.new'), '新会话');
});

test('core session helpers follow the injected locale and leave server data untouched', async () => {
  const outfile = path.join(outDir, 'core.mjs');
  buildSync({
    entryPoints: [path.join(coreSrc, 'index.ts')],
    bundle: true,
    platform: 'node',
    format: 'esm',
    outfile,
  });
  const core = await import(pathToFileURL(outfile));
  const { createTranslator } = await buildCoreI18n();

  const now = Date.parse('2026-08-18T10:00:00Z');
  assert.equal(core.formatSessionTime('2026-08-18T09:59:40Z', now), '刚刚');
  assert.equal(core.formatSessionTime('2026-08-18T09:59:40Z', now, createTranslator('en')), 'just now');
  assert.equal(core.formatSessionTime('2026-08-17T10:00:00Z', now, createTranslator('en')), 'yesterday');

  // 后端返回的 title 原样展示，不被词条覆盖
  const serverTitle = [{ session_id: 's1', title: '巡检磁盘水位' }];
  assert.equal(core.mapPlatformSessions(serverTitle)[0].title, '巡检磁盘水位');
  assert.equal(core.mapPlatformSessions(serverTitle, createTranslator('en'))[0].title, '巡检磁盘水位');
  // 缺 title 时才用词条兜底
  assert.equal(core.mapPlatformSessions([{ session_id: 's2' }])[0].title, '新会话');
  assert.equal(core.mapPlatformSessions([{ session_id: 's2' }], createTranslator('en'))[0].title, 'New conversation');
});

test('previously hardcoded Chinese literals no longer bypass i18n', () => {
  // 不做「源码里是否还有中文」的启发式扫描——那种判定对 JSX 与跨行实参过于脆弱。
  // 改为锁定迁移前确实写死、现在必须经词条取值的具体字面量。
  const literals = [
    '发一条消息开始对话',
    '正在分析工具结果',
    '正在整理思路',
    '暂无会话',
    '还没有可对话的智能体',
    '请先发布智能体',
    '已复制到剪贴板',
    '分钟前',
    '刚刚',
    '思考中',
  ];

  const sources = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (/\.tsx?$/.test(entry.name)) {
        sources.push([path.relative(rootDir, full), stripComments(fs.readFileSync(full, 'utf8'))]);
      }
    }
  };
  walk(uiSrc);
  walk(coreSrc);

  const offenders = [];
  for (const [file, lines] of sources) {
    lines.forEach((code, index) => {
      for (const literal of literals) {
        if (!code.includes(literal)) continue;
        // 允许：t('key', '中文兜底') 与词条表条目
        const escaped = literal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const inTranslateCall = new RegExp(`\\b(t|translate)\\([^,]*,\\s*'[^']*${escaped}`).test(code);
        const isCatalogEntry = /^\s*'[^']+'\s*:\s*'/.test(code);
        if (inTranslateCall || isCatalogEntry) continue;
        offenders.push(`${file}:${index + 1} ${literal} | ${code.trim()}`);
      }
    });
  }

  assert.deepEqual(offenders, [], `Chinese literal bypassed i18n:\n${offenders.join('\n')}`);
});

test('components render English for locale=en and Chinese otherwise', async () => {
  // 必须打进同一个 bundle：分开构建会让 @webchat/core 各得一份副本，
  // TranslatorContext 与翻译函数不在同一模块实例里，locale 传不下去。
  const entry = path.join(outDir, 'entry.ts');
  fs.writeFileSync(
    entry,
    [
      `export { WebChatLocaleProvider } from ${JSON.stringify(path.join(uiSrc, 'useTranslator').replace(/\\/g, '/'))};`,
      `export { MessageActions, COPY_SUCCESS_LABEL_KEY } from ${JSON.stringify(path.join(uiSrc, 'components/MessageActions').replace(/\\/g, '/'))};`,
    ].join('\n'),
    'utf8',
  );
  buildSync({
    entryPoints: [entry],
    bundle: true,
    platform: 'node',
    format: 'esm',
    jsx: 'automatic',
    outfile: path.join(outDir, 'components.mjs'),
    external: ['react', 'react/jsx-runtime'],
    alias: {
      '@webchat/core': path.join(coreSrc, 'index.ts'),
      'react-dom': path.join(rootDir, 'tests/react-dom.portal-capture.stub.mjs'),
    },
    loader: { '.css': 'empty' },
  });

  const React = (await import('react')).default;
  const { create, act } = await import('react-test-renderer');
  const { MessageActions, WebChatLocaleProvider, COPY_SUCCESS_LABEL_KEY } = await import(
    pathToFileURL(path.join(outDir, 'components.mjs'))
  );

  const render = async (locale) => {
    let renderer;
    await act(async () => {
      renderer = create(
        React.createElement(
          WebChatLocaleProvider,
          { locale },
          React.createElement(MessageActions, {
            messageId: 'm1',
            messageContent: 'hello',
            isBot: true,
            isLastBotMessage: true,
            showActions: true,
          }),
        ),
      );
    });
    return renderer;
  };

  const zhRenderer = await render('zh');
  assert.ok(zhRenderer.root.findByProps({ 'aria-label': '复制' }), 'zh renders 复制');
  assert.equal(zhRenderer.root.findByProps({ title: '重新生成' }).props.title, '重新生成');

  const enRenderer = await render('en');
  assert.equal(enRenderer.root.findAllByProps({ 'aria-label': '复制' }).length, 0, 'no 复制 in en');
  assert.ok(enRenderer.root.findByProps({ 'aria-label': 'Copy' }), 'en renders Copy');
  assert.equal(enRenderer.root.findByProps({ title: 'Regenerate' }).props.title, 'Regenerate');
  assert.equal(enRenderer.root.findByProps({ title: 'Delete' }).props.title, 'Delete');

  assert.equal(COPY_SUCCESS_LABEL_KEY, 'message.copied');
});
