/**
 * 外部登录结果页关闭标签契约。
 *
 * 锁定:
 *   - 结果页只渲染 LoginAuthResultContent
 *   - 关闭动作先唤回原登录标签(postMessage / opener.focus / 具名 window.open)再 window.close()
 *   - close 失败后展示 closeFailed 文案
 *   - 不把本标签导航回 /auth/signin
 */
import * as assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, '..');
const pagePath = resolve(webRoot, 'src/app/(core)/auth/signin/login-auth-result/page.tsx');
const contentPath = resolve(
  webRoot,
  'src/app/(core)/auth/signin/login-auth-result/LoginAuthResultContent.tsx',
);
const signinClientPath = resolve(webRoot, 'src/app/(core)/auth/signin/SigninClient.tsx');
const zhPath = resolve(webRoot, 'src/locales/zh.json');
const enPath = resolve(webRoot, 'src/locales/en.json');

const failures: string[] = [];

function read(path: string) {
  return readFileSync(path, 'utf8');
}

if (!existsSync(pagePath)) {
  failures.push('[page.tsx] 缺少 login-auth-result 页面');
} else {
  const src = read(pagePath);
  if (!src.includes('LoginAuthResultContent')) {
    failures.push('[page.tsx] 必须渲染 LoginAuthResultContent');
  }
  if (/window\.location|router\.push|href=["']\/auth\/signin/.test(src)) {
    failures.push('[page.tsx] 不得把本标签导航回 /auth/signin');
  }
}

if (!existsSync(contentPath)) {
  failures.push('[LoginAuthResultContent.tsx] 缺少关闭标签组件');
} else {
  const src = read(contentPath);
  if (!/'use client'/.test(src)) {
    failures.push('[LoginAuthResultContent.tsx] 必须是 client 组件');
  }
  if (!/opener\.focus\(/.test(src)) {
    failures.push('[LoginAuthResultContent.tsx] 关闭前必须 opener.focus()');
  }
  if (!/postMessage\(/.test(src) || !/LOGIN_AUTH_RESULT_RETURN_MESSAGE/.test(src)) {
    failures.push('[LoginAuthResultContent.tsx] 关闭前必须 postMessage 通知原登录标签');
  }
  if (!/window\.open\(\s*['"]['"]\s*,\s*SIGNIN_WINDOW_NAME/.test(src)) {
    failures.push('[LoginAuthResultContent.tsx] 关闭前必须用具名 window.open 唤回原登录标签');
  }
  if (!/window\.close\(/.test(src)) {
    failures.push('[LoginAuthResultContent.tsx] 必须调用 window.close()');
  }
  if (!/setCloseFailed\(true\)/.test(src) || !/signin\.loginAuth\.result\.closeFailed/.test(src)) {
    failures.push('[LoginAuthResultContent.tsx] close 失败必须展示 closeFailed 文案');
  }
  if (/href=["']\/auth\/signin|router\.push\(['"]\/auth\/signin/.test(src)) {
    failures.push('[LoginAuthResultContent.tsx] 不得把本标签导航回 /auth/signin');
  }
}

if (!existsSync(signinClientPath)) {
  failures.push('[SigninClient.tsx] 缺少登录页组件');
} else {
  const src = read(signinClientPath);
  if (!/window\.name\s*=\s*SIGNIN_WINDOW_NAME/.test(src)) {
    failures.push('[SigninClient.tsx] 全页登录必须声明 window.name');
  }
  if (!/LOGIN_AUTH_RESULT_RETURN_MESSAGE/.test(src) || !/window\.focus\(/.test(src)) {
    failures.push('[SigninClient.tsx] 必须监听结果页回跳消息并 window.focus()');
  }
}

type Nested = { [key: string]: string | Nested };

function flattenMessages(obj: Nested, prefix = ''): Record<string, string> {
  return Object.keys(obj).reduce((acc: Record<string, string>, key) => {
    const value = obj[key];
    const prefixedKey = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      acc[prefixedKey] = value;
    } else {
      Object.assign(acc, flattenMessages(value, prefixedKey));
    }
    return acc;
  }, {});
}

const requiredKeys = [
  'signin.loginAuth.result.titleSuccess',
  'signin.loginAuth.result.titleCancelled',
  'signin.loginAuth.result.titleExpired',
  'signin.loginAuth.result.titleFailed',
  'signin.loginAuth.result.defaultMessage',
  'signin.loginAuth.result.closeTab',
  'signin.loginAuth.result.closeFailed',
] as const;

const locales = {
  zh: flattenMessages(JSON.parse(read(zhPath))),
  en: flattenMessages(JSON.parse(read(enPath))),
};

for (const key of requiredKeys) {
  if (!locales.zh[key]?.trim()) {
    failures.push(`[zh.json] 缺少 ${key}`);
  }
  if (!locales.en[key]?.trim()) {
    failures.push(`[en.json] 缺少 ${key}`);
  }
}

assert.equal(
  failures.length,
  0,
  `\nlogin-auth-result close-tab 契约失败:\n  - ${failures.join('\n  - ')}`,
);

console.log('login-auth-result close-tab test passed');
