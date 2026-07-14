/**
 * 登录页双语切换器回归测试。
 *
 * 背景:OpenSpec change `add-signin-language-toggle` 在登录页 page mode
 * 标题区右上角新增 <SigninLanguageToggle/>。本测试锁定组件契约与
 * 接入点,防止后续重构把行为再次陷回:
 *   - 引入 fetch / useSession / try-catch(违反"切语言不分发请求"边界)
 *   - 把组件挂到 modal mode 渲染树
 *   - 漏写 signin.languageToggle i18n 键的双侧对齐
 *
 * 风格与本仓库约定一致:web 没有 RTL/Jest 配置,采用
 * `web/scripts/<name>-test.ts` 形式,通过 fs.readFileSync + 正则
 * 断言源码契约,不构造 React 运行时。
 *
 * 失败即视为组件契约缺失或被错误改动。
 */

import * as assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, '..');

const componentPath = resolve(
  webRoot,
  'src/app/(core)/auth/signin/login-auth/SigninLanguageToggle.tsx',
);
const signinClientPath = resolve(
  webRoot,
  'src/app/(core)/auth/signin/SigninClient.tsx',
);
const zhPath = resolve(webRoot, 'src/locales/zh.json');
const enPath = resolve(webRoot, 'src/locales/en.json');

const failures: string[] = [];

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

// —— 组件契约 ————————————————————————————————————————————————————
if (!existsSync(componentPath)) {
  failures.push(`[SigninLanguageToggle.tsx] 缺少组件文件`);
} else {
  const src = read(componentPath);

  // 1.2 trigger 用 SUPPORTED_LANGUAGES.find(... === locale) 解析当前
  if (
    !/SUPPORTED_LANGUAGES[\s\S]*?\.find\s*\(\s*\(\s*lang\s*\)\s*=>\s*lang\.key\s*===\s*locale\s*\)/.test(
      src,
    )
  ) {
    failures.push(
      '[SigninLanguageToggle.tsx] trigger 未基于 SUPPORTED_LANGUAGES.find(lang.key === locale) 解析当前语言',
    );
  }

  // 1.3 aria-label 走 i18n 键 signin.languageToggle.label
  if (
    !/aria-label\s*=\s*\{\s*t\(\s*['"]signin\.languageToggle\.label['"]\s*\)\s*\}/.test(src)
  ) {
    failures.push(
      '[SigninLanguageToggle.tsx] trigger 缺 aria-label={t("signin.languageToggle.label")} 字面量',
    );
  }

  // 1.4 Dropdown 用 .filter(!== locale) 仅展示另一语言
  if (
    !/SUPPORTED_LANGUAGES[\s\S]*?\.filter\s*\(\s*\(\s*lang\s*\)\s*=>\s*lang\.key\s*!==\s*locale\s*\)/.test(
      src,
    )
  ) {
    failures.push(
      '[SigninLanguageToggle.tsx] Dropdown 项未用 .filter(lang => lang.key !== locale) 过滤当前语言',
    );
  }

  // 1.5 点击目标语言 → setLocale(lang.key)(放宽:inline popover 与
  //           antd menu 的 onClick 形态都允许,只要源里出现
  //           `setLocale(lang.key)` 调用即可)
  if (!/setLocale\(\s*lang\.key\s*\)/.test(src)) {
    failures.push(
      '[SigninLanguageToggle.tsx] 点击目标语言未调 setLocale(lang.key)',
    );
  }

  // 1.6 不引入 fetch / useSession / try-catch
  if (/\bfetch\s*\(/.test(src)) {
    failures.push('[SigninLanguageToggle.tsx] 组件内不应出现 fetch( 调用');
  }
  if (/\buseSession\s*\(/.test(src)) {
    failures.push('[SigninLanguageToggle.tsx] 组件内不应引入 useSession');
  }
  if (/\btry\s*\{[\s\S]*?\bcatch\s*\(/.test(src)) {
    failures.push(
      '[SigninLanguageToggle.tsx] 组件内不应有 try-catch(LocaleProvider.changeLocale 内部已处理)',
    );
  }

  // 必须使用 useLocale().setLocale,不允许 setLocale 参数是常量
  if (!/setLocale\(\s*lang\.key\s*\)/.test(src)) {
    failures.push(
      '[SigninLanguageToggle.tsx] setLocale 调用未传 lang.key(违反动态选择)',
    );
  }
}

// —— i18n 键双侧对齐 ————————————————————————————————————————————
type Nested = { [key: string]: string | Nested };

function flattenMessages(
  obj: Nested,
  prefix = '',
): Record<string, string> {
  return Object.keys(obj).reduce(
    (acc: Record<string, string>, key) => {
      const value = obj[key];
      const prefixedKey = prefix ? `${prefix}.${key}` : key;
      if (typeof value === 'string') {
        acc[prefixedKey] = value;
      } else {
        Object.assign(acc, flattenMessages(value, prefixedKey));
      }
      return acc;
    },
    {},
  );
}

type Locale = 'zh' | 'en';
const REQUIRED_KEYS: ReadonlyArray<string> = [
  'signin.languageToggle.label',
  'signin.languageToggle.zhItem',
  'signin.languageToggle.enItem',
];
const locales: Record<Locale, Record<string, string>> = {
  zh: flattenMessages(JSON.parse(read(zhPath))),
  en: flattenMessages(JSON.parse(read(enPath))),
};

for (const key of REQUIRED_KEYS) {
  if (locales.zh[key] === undefined) {
    failures.push(`[zh.json] 缺少 i18n 键 ${key}`);
  }
  if (locales.en[key] === undefined) {
    failures.push(`[en.json] 缺少 i18n 键 ${key}`);
  }
}

// —— SigninClient 接入 —————————————————————————————————————————
if (!existsSync(signinClientPath)) {
  failures.push('[SigninClient.tsx] 不存在(预期不应发生)');
} else {
  const sc = read(signinClientPath);

  // import
  if (
    !/import\s+SigninLanguageToggle\s+from\s+['"][^'"]*login-auth\/SigninLanguageToggle['"]/.test(
      sc,
    )
  ) {
    failures.push(
      '[SigninClient.tsx] 缺 import SigninLanguageToggle from "./login-auth/SigninLanguageToggle"',
    );
  }

  // page mode 渲染树挂载(必存在一处 <SigninLanguageToggle />)
  if (!/<SigninLanguageToggle\s*\/\s*>/.test(sc)) {
    failures.push('[SigninClient.tsx] 未挂载 <SigninLanguageToggle />');
  }

  // modal mode 渲染树必须不挂
  if (
    /if\s*\(\s*mode\s*===\s*['"]modal['"]\s*\)[\s\S]{0,500}?<SigninLanguageToggle/.test(
      sc,
    )
  ) {
    failures.push('[SigninClient.tsx] modal mode 不该挂载 SigninLanguageToggle');
  }
}

assert.equal(
  failures.length,
  0,
  '\n[signin-language-toggle] 回归测试失败:\n  - ' + failures.join('\n  - '),
);

console.log('signin language toggle test passed');
