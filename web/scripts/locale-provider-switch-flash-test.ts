/**
 * LocaleProvider 切换语言闪烁回归。
 *
 * 锁定 `fix-locale-provider-switch-flash` 变更的回归行为：
 *   - `fetchLocaleMessages` 函数体内不再管控 `isLoading`,
 *     loading 状态完全由 useEffect 初始化路径显式管控。
 *   - 初始化 fetch 的 finally 必须检查 cancelled：Strict Mode 卸载不得
 *     把空 messages 交给 IntlProvider。
 *   - `changeLocale` 仍后台调用 `fetchLocaleMessages` 拉新 messages,
 *     但**不**触发 `<Spin/>` 卸载整页 children —— 这正是"切语言不闪"的关键。
 *
 * 风格:沿用仓库 `web/scripts/<name>-test.ts` 约定,
 * 通过 fs.readFileSync + 正则断言源码契约,不构造 React 运行时。
 */

import * as assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const localePath = resolve(here, '../src/context/locale.tsx');
const failures: string[] = [];

if (!existsSync(localePath)) {
  failures.push('[locale.tsx] 文件不存在');
} else {
  const src = readFileSync(localePath, 'utf8');

  // —— 工具函数:从源码里抽出指定函数体 ————————————————
  function extractFunctionBody(name: string): string | null {
    const re = new RegExp(
      `const\\s+${name}\\s*=\\s*(?:async\\s*)?\\([^)]*\\)\\s*=>\\s*\\{[\\s\\S]*?^\\s*\\};`,
      'm',
    );
    const m = src.match(re);
    return m ? m[0] : null;
  }

  // 1. fetchLocaleMessages 函数体内**不应**出现 setIsLoading(
  //    (loading 完全由 useEffect 初始化路径显式管控)
  const fetchFnBody = extractFunctionBody('fetchLocaleMessages');
  if (fetchFnBody === null) {
    failures.push('[locale.tsx] 找不到 fetchLocaleMessages 函数体');
  } else if (/\bsetIsLoading\s*\(/.test(fetchFnBody)) {
    failures.push(
      '[locale.tsx] fetchLocaleMessages 内不应调 setIsLoading(' +
        '(loading 由 useEffect 初始化路径显式管控)',
    );
  }

  // 3. useEffect 初始化路径必须在仍有效的 effect 里关闭 loading。
  //    不得无条件 .finally(() => setIsLoading(false))：React Strict Mode
  //    会先卸载再挂载，第一次 fetch 的 finally 若关掉 loading，会把空 messages
  //    交给 IntlProvider，刷出整页 MISSING_TRANSLATION。
  const initUseEffectRe =
    /useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?\bsetLocale\s*\(\s*savedLocale\s*\)\s*;[\s\S]*?\}\s*,\s*\[\s*\]\s*\)/m;
  const initUseEffectBlock = src.match(initUseEffectRe);
  if (initUseEffectBlock === null) {
    failures.push('[locale.tsx] 找不到含 `setLocale(savedLocale)` 的初始化 useEffect');
  } else {
    const block = initUseEffectBlock[0];
    if (!/\blet\s+cancelled\s*=\s*false/.test(block)) {
      failures.push('[locale.tsx] useEffect 初始化路径必须用 cancelled 标记过期的 Strict Mode 卸载');
    }
    if (!/\bsetIsLoading\s*\(\s*true\s*\)/.test(block)) {
      failures.push('[locale.tsx] useEffect 初始化路径必须 setIsLoading(true)');
    }
    if (
      /finally\s*\(\s*\(\s*\)\s*=>\s*setIsLoading\s*\(\s*false\s*\)\s*\)/.test(
        block,
      )
    ) {
      failures.push(
        '[locale.tsx] 初始化 fetch 的 finally 不得无条件 setIsLoading(false)',
      );
    }
    if (
      !/finally\s*\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?\bcancelled[\s\S]*?setIsLoading\s*\(\s*false\s*\)/.test(
        block,
      )
    ) {
      failures.push(
        '[locale.tsx] useEffect 初始化路径必须在 fetch 后 .finally 且仅当 !cancelled 时 setIsLoading(false)',
      );
    }
    if (!/return\s*\(\s*\)\s*=>\s*\{\s*cancelled\s*=\s*true/.test(block)) {
      failures.push('[locale.tsx] 初始化 useEffect cleanup 必须 cancelled = true');
    }
  }

  // 4. changeLocale 内**仍调用** fetchLocaleMessages(...),后台拉新 messages
  const changeFnBody = extractFunctionBody('changeLocale');
  if (changeFnBody === null) {
    failures.push('[locale.tsx] 找不到 changeLocale 函数体');
  } else if (!/\bfetchLocaleMessages\s*\(/.test(changeFnBody)) {
    failures.push(
      '[locale.tsx] changeLocale 内必须调 fetchLocaleMessages(切语言后台拉新 messages)',
    );
  }

  // 5. 全局不应出现"调用 fetchLocaleMessages 然后链式 setIsLoading"
  //    (强约束:不允许把 setIsLoading 延迟到调用方)
  if (
    /fetchLocaleMessages\s*\([\s\S]{0,80}\.setIsLoading\s*\(/.test(src)
  ) {
    failures.push(
      '[locale.tsx] 不应在 fetchLocaleMessages(...) 调用链上设 isLoading',
    );
  }
}

assert.equal(
  failures.length,
  0,
  '\n[locale-provider-switch-flash] 回归失败:\n  - ' + failures.join('\n  - '),
);

console.log('locale provider switch flash test passed');
