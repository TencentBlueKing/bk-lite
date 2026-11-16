import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import * as sass from 'sass';
import postcss from 'postcss';
import tailwindcss from '@tailwindcss/postcss';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const viteRequire = createRequire(createRequire(require.resolve('vitest/package.json')).resolve('vite/package.json'));
const { build } = viteRequire('esbuild');
// 保留真实 Inspector、OperateModal 和 AntD；隔离与弹窗定位无关的业务依赖。
const stubs = {
  '@/utils/i18n': 'export const useTranslation = () => ({ t: (_key, fallback) => fallback });',
  './workflow-permission': 'export const WorkflowPermission = ({ children }) => children;',
  './json-code-view': 'export const JsonCodeView = () => null;',
  './schema-node-form': 'export const WORKFLOW_REFERENCE_MIME = "text/plain";',
};
const bundle = await build({
  stdin: {
    contents: `
      import React from 'react';
      import { createRoot } from 'react-dom/client';
      import { ConfigProvider, theme } from 'antd';
      import { createThemeCss, applyThemeMode } from './src/theme/css-adapter';
      import { defaultTheme } from './src/theme/defaults';
      import { WorkflowNodeInspector } from './src/app/workflow/components/workflow-editor-surface';
      const themeStyle = document.createElement('style');
      themeStyle.textContent = createThemeCss(defaultTheme);
      document.head.appendChild(themeStyle);
      window.renderInspector = (open, dark = false) => root.render(
        <ConfigProvider theme={{ token: { motion: false }, algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}>
          <WorkflowNodeInspector open={open} title="发送巡检通知" meta="bklite_notification"
            references={[]} readOnly={false} onClose={() => window.renderInspector(false)}>
            <label>节点名称<input defaultValue="发送巡检通知" /></label>
          </WorkflowNodeInspector>
        </ConfigProvider>
      );
      const root = createRoot(document.getElementById('root'));
      window.applyThemeMode = applyThemeMode;
      window.renderInspector(true);
    `,
    resolveDir: root,
    loader: 'tsx',
  },
  bundle: true,
  write: false,
  outdir: '/tmp/bklite-inspector-layout',
  jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"' },
  plugins: [{
    name: 'layout-fixture',
    setup(builder) {
      builder.onResolve({ filter: /.*/ }, ({ path }) => path in stubs ? { path, namespace: 'stub' } : undefined);
      builder.onLoad({ filter: /.*/, namespace: 'stub' }, ({ path }) => ({ contents: stubs[path], loader: 'js' }));
      builder.onLoad({ filter: /\.module\.scss$/ }, ({ path }) => ({ contents: sass.compile(path).css, loader: 'local-css' }));
    },
  }],
});
const css = await readFile(resolve(root, 'src/app/(core)/components/global-webchat/global-webchat.css'), 'utf8');
const utilities = await postcss([tailwindcss()]).process(
  '@import "tailwindcss" source(none); @source "../src/app/workflow/components/workflow-editor-surface.tsx";',
  { from: resolve(root, 'scripts/inspector-fixture.css') },
);
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setContent('<html><head></head><body><div id="root"></div></body></html>');
  await page.addStyleTag({ content: utilities.css });
  await page.addStyleTag({ content: css });
  for (const file of bundle.outputFiles) {
    if (file.path.endsWith('.css')) await page.addStyleTag({ content: file.text });
    else await page.addScriptTag({ content: file.text });
  }
  for (const [width, height] of [[1920, 930], [1440, 900], [1280, 800]]) {
    await page.setViewportSize({ width, height });
    for (const dock of [0, 380, 480, 0]) {
      for (const dark of [false, true]) {
        await page.evaluate(({ dock, dark }) => {
          document.documentElement.style.setProperty('--bk-webchat-dock-width', `${dock}px`);
          window.applyThemeMode(dark ? 'dark' : 'light');
          window.renderInspector(true, dark);
        }, { dock, dark });
        const dialog = page.getByRole('dialog');
        await dialog.waitFor({ state: 'visible' });
        const box = await dialog.boundingBox();
        const state = `${width}x${height}, dock=${dock}, dark=${dark}: ${JSON.stringify(box)}`;
        if (process.env.LAYOUT_SCREENSHOT_PATH && width === 1920 && dock === 380 && !dark) {
          await page.screenshot({ path: process.env.LAYOUT_SCREENSHOT_PATH });
        }
        assert.ok(box && box.y >= 0 && box.y + box.height <= height + 1, `弹窗必须完整位于当前视口: ${state}`);
        assert.ok(box.x >= 15 && box.x + box.width <= width - dock - 15, `弹窗必须位于对话栏左侧并保留边距: ${state}`);
        assert.ok(Math.abs(box.x + box.width / 2 - (width - dock) / 2) <= 1, `弹窗必须在工作区居中: ${state}`);
        await page.getByRole('button', { name: 'Close', exact: true }).click();
        await dialog.waitFor({ state: 'hidden' });
      }
    }
  }
  assert.deepEqual(errors, []);
  console.log('PASS: Inspector 在 3 个视口、对话栏开关/缩放、明暗主题和重开场景中始终可见并居中');
} finally {
  await browser.close();
}
