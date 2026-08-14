/**
 * 控制台「初始化用户配置」误弹窗回归。
 *
 * 锁定：login_info 返回前，首屏不得把用户当成首次登录。
 * 旧实现把 isFirstLogin 默认 true、loading 默认 false，useEffect 拉
 * /core/api/login_info/ 之前已经完成一次绘制，已初始化用户会闪出弹窗；
 * login_info 较慢时能看清，缓存命中后再登则一闪而过，表现为「有时出现、再登没有」。
 *
 * 风格: 沿用仓库 web/scripts/<name>-test.ts 约定，通过源码契约断言，不构造 React 运行时。
 */

import * as assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const userInfoPath = resolve(here, '../src/context/userInfo.tsx');
const homePath = resolve(here, '../src/app/ops-console/(pages)/home/page.tsx');
const failures: string[] = [];

function readFlagInit(src: string, stateName: string): string | null {
  const re = new RegExp(
    `const \\[${stateName},\\s*\\w+\\] = useState<boolean>\\((true|false)\\)`,
  );
  return src.match(re)?.[1] ?? null;
}

if (!existsSync(userInfoPath)) {
  failures.push('[userInfo.tsx] 文件不存在');
} else {
  const src = readFileSync(userInfoPath, 'utf8');
  const loadingInit = readFlagInit(src, 'loading');
  const firstLoginInit = readFlagInit(src, 'isFirstLogin');

  if (loadingInit === null) {
    failures.push('[userInfo.tsx] 找不到 loading 的 boolean useState 初值');
  }
  if (firstLoginInit === null) {
    failures.push('[userInfo.tsx] 找不到 isFirstLogin 的 boolean useState 初值');
  }

  if (loadingInit !== null && firstLoginInit !== null) {
    const showsModalBeforeLoginInfo =
      firstLoginInit === 'true' && loadingInit === 'false';
    if (showsModalBeforeLoginInfo) {
      failures.push(
        '[userInfo.tsx] login_info 返回前不得弹出初始化用户配置：' +
          `isFirstLogin 初值=${firstLoginInit} 且 loading 初值=${loadingInit}。` +
          '应将 loading 初值设为 true，且 isFirstLogin 初值设为 false。',
      );
    }
    if (loadingInit !== 'true') {
      failures.push(
        `[userInfo.tsx] loading 必须默认 true，避免首屏在 fetch 前把 !userLoading 当成已就绪`,
      );
    }
    if (firstLoginInit !== 'false') {
      failures.push(
        `[userInfo.tsx] isFirstLogin 必须默认 false，失败/未返回时不得当成首次登录`,
      );
    }
  }
}

if (!existsSync(homePath)) {
  failures.push('[ops-console home] 文件不存在');
} else {
  const src = readFileSync(homePath, 'utf8');
  if (!/visible=\{isFirstLogin && !userLoading\}/.test(src)) {
    failures.push(
      '[ops-console home] 初始化弹窗必须同时要求 isFirstLogin 且用户信息已加载完',
    );
  }
}

if (failures.length) {
  for (const failure of failures) {
    console.error(`✗ ${failure}`);
  }
  process.exit(1);
}

console.log('✓ 初始化用户配置弹窗不会在 login_info 返回前误弹出');
