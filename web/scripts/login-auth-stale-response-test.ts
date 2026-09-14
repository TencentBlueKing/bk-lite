/**
 * 登录认证弹窗卸载后必须丢弃迟到的第三方认证响应。
 *
 * 覆盖:
 *   - 卸载后迟到 start 不得 window.open，且不得留下 interval
 *   - 卸载后迟到 success 不得 onSessionSync
 *   - 新流程替换旧流程后旧回调丢弃
 *   - 有效 generation 仍可 open / poll / sync
 */
import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createLoginAuthRequestGuard } from '../src/app/(core)/auth/signin/login-auth/loginAuthRequestGuard.ts';

const here = dirname(fileURLToPath(import.meta.url));
const hookPath = resolve(
  here,
  '../src/app/(core)/auth/signin/login-auth/useLoginAuthValidation.ts',
);
const guardPath = resolve(
  here,
  '../src/app/(core)/auth/signin/login-auth/loginAuthRequestGuard.ts',
);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

interface LoginAuthSession {
  openedUrls: string[];
  intervalIds: number[];
  otpCount: number;
  syncCount: number;
  start: (loginUrl: string, startPromise: Promise<void>) => Promise<number>;
  applyOtp: (generation: number) => void;
  applySuccess: (generation: number, pollPromise: Promise<void>) => Promise<void>;
  unmount: () => void;
  replaceStart: (loginUrl: string, startPromise: Promise<void>) => Promise<number>;
}

function createLoginAuthSession(): LoginAuthSession {
  const guard = createLoginAuthRequestGuard();
  const openedUrls: string[] = [];
  const intervalIds: number[] = [];
  const counts = { otpCount: 0, syncCount: 0 };
  let nextIntervalId = 1;

  const clearIntervals = () => {
    intervalIds.length = 0;
  };

  const startWithGeneration = async (loginUrl: string, startPromise: Promise<void>) => {
    const generation = guard.begin();
    await startPromise;
    if (!guard.shouldContinue(generation)) {
      return generation;
    }
    openedUrls.push(loginUrl);
    if (!guard.shouldContinue(generation)) {
      return generation;
    }
    intervalIds.push(nextIntervalId);
    nextIntervalId += 1;
    return generation;
  };

  return {
    openedUrls,
    intervalIds,
    get otpCount() {
      return counts.otpCount;
    },
    get syncCount() {
      return counts.syncCount;
    },
    async start(loginUrl, startPromise) {
      guard.invalidate();
      return startWithGeneration(loginUrl, startPromise);
    },
    applyOtp(generation) {
      if (!guard.shouldContinue(generation)) {
        return;
      }
      counts.otpCount += 1;
    },
    async applySuccess(generation, pollPromise) {
      await pollPromise;
      if (!guard.shouldContinue(generation)) {
        return;
      }
      counts.syncCount += 1;
    },
    unmount() {
      guard.invalidate();
      clearIntervals();
    },
    async replaceStart(loginUrl, startPromise) {
      clearIntervals();
      guard.invalidate();
      return startWithGeneration(loginUrl, startPromise);
    },
  };
}

function extractFunctionBody(source: string, name: string): string {
  const marker = `const ${name} =`;
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, `缺少 ${name}`);
  let depth = 0;
  let started = false;
  for (let index = start; index < source.length; index += 1) {
    const char = source[index];
    if (char === '{') {
      depth += 1;
      started = true;
    } else if (char === '}') {
      depth -= 1;
      if (started && depth === 0) {
        return source.slice(start, index + 1);
      }
    }
  }
  throw new Error(`未能解析 ${name}`);
}

function assertShouldContinueBefore(body: string, token: string, label: string) {
  const continueIndex = body.lastIndexOf('shouldContinue', body.indexOf(token));
  const tokenIndex = body.indexOf(token);
  assert.ok(
    continueIndex !== -1 && tokenIndex !== -1 && continueIndex < tokenIndex,
    `${label} 必须在 ${token} 之前检查 shouldContinue`,
  );
}

async function main() {
  const guard = createLoginAuthRequestGuard();
  const staleGeneration = guard.begin();
  guard.invalidate();
  assert.equal(
    guard.shouldContinue(staleGeneration),
    false,
    '卸载 invalidate 后迟到 generation 不得继续',
  );

  const liveGuard = createLoginAuthRequestGuard();
  const liveGeneration = liveGuard.begin();
  assert.equal(
    liveGuard.shouldContinue(liveGeneration),
    true,
    '有效 generation 必须可以继续',
  );

  const unmountedStart = createLoginAuthSession();
  const lateStart = deferred<void>();
  const lateStartGenerationPromise = unmountedStart.start('https://idp.example/login', lateStart.promise);
  unmountedStart.unmount();
  lateStart.resolve();
  await lateStartGenerationPromise;
  assert.deepEqual(unmountedStart.openedUrls, [], '卸载后迟到 start 不得 window.open');
  assert.deepEqual(unmountedStart.intervalIds, [], '卸载后迟到 start 不得留下 interval');

  const unmountedSuccess = createLoginAuthSession();
  const startReady = deferred<void>();
  const successGenerationPromise = unmountedSuccess.start('https://idp.example/ok', startReady.promise);
  startReady.resolve();
  const successGeneration = await successGenerationPromise;
  assert.deepEqual(unmountedSuccess.openedUrls, ['https://idp.example/ok']);
  assert.equal(unmountedSuccess.intervalIds.length, 1, '有效 start 可以留下轮询 interval');

  const latePoll = deferred<void>();
  const applySuccessPromise = unmountedSuccess.applySuccess(successGeneration, latePoll.promise);
  unmountedSuccess.unmount();
  latePoll.resolve();
  await applySuccessPromise;
  assert.equal(unmountedSuccess.syncCount, 0, '卸载后迟到 success 不得 onSessionSync');

  const replaced = createLoginAuthSession();
  const oldStart = deferred<void>();
  const oldGenerationPromise = replaced.start('https://idp.example/old', oldStart.promise);
  const newStart = deferred<void>();
  const newGenerationPromise = replaced.replaceStart('https://idp.example/new', newStart.promise);
  oldStart.resolve();
  const oldGeneration = await oldGenerationPromise;
  newStart.resolve();
  const newGeneration = await newGenerationPromise;
  assert.deepEqual(replaced.openedUrls, ['https://idp.example/new'], '新流程替换后旧 start 不得 open');
  assert.deepEqual(replaced.intervalIds, [1], '只有新流程可以留下 interval');

  const oldPoll = deferred<void>();
  const oldSyncPromise = replaced.applySuccess(oldGeneration, oldPoll.promise);
  oldPoll.resolve();
  await oldSyncPromise;
  assert.equal(replaced.syncCount, 0, '被替换的旧流程不得 onSessionSync');

  replaced.applyOtp(oldGeneration);
  assert.equal(replaced.otpCount, 0, '被替换的旧流程不得 onOtpRequired');

  const livePoll = deferred<void>();
  const liveSyncPromise = replaced.applySuccess(newGeneration, livePoll.promise);
  livePoll.resolve();
  await liveSyncPromise;
  assert.equal(replaced.syncCount, 1, '有效 generation 仍可 onSessionSync');
  replaced.applyOtp(newGeneration);
  assert.equal(replaced.otpCount, 1, '有效 generation 仍可 onOtpRequired');

  const hookSource = readFileSync(hookPath, 'utf8');
  const guardSource = readFileSync(guardPath, 'utf8');

  assert.match(guardSource, /generation/, 'guard 必须维护 generation');
  assert.match(guardSource, /alive/, 'guard 必须维护 alive');
  assert.match(hookSource, /from ['"]\.\/loginAuthRequestGuard['"]/, 'hook 必须 import 抽出的 guard');
  assert.match(hookSource, /createLoginAuthRequestGuard/, 'hook 必须创建 login auth request guard');
  assert.match(
    hookSource,
    /return\s*\(\)\s*=>\s*\{[\s\S]*requestGuard\.invalidate\(\)[\s\S]*window\.clearInterval/,
    '卸载必须 invalidate，并仍 clearInterval',
  );

  const startBody = extractFunctionBody(hookSource, 'startLoginAuth');
  assert.match(startBody, /requestGuard\.invalidate\(\)/, '新 start 必须 invalidate 旧流程');
  assert.match(startBody, /requestGuard\.begin\(\)/, '新 start 必须 begin 新 generation');
  assertShouldContinueBefore(startBody, 'window.open', 'startLoginAuth');
  assertShouldContinueBefore(startBody, 'setInterval', 'startLoginAuth');

  const pollBody = extractFunctionBody(hookSource, 'pollStatus');
  assert.match(pollBody, /shouldContinue/, 'pollStatus 每个 await 后必须检查存活');

  const terminalBody = extractFunctionBody(hookSource, 'resolveTerminalStatus');
  assertShouldContinueBefore(terminalBody, 'onOtpRequired', 'resolveTerminalStatus');
  assertShouldContinueBefore(terminalBody, 'onSessionSync', 'resolveTerminalStatus');

  console.log('login-auth-stale-response-test: ok');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
