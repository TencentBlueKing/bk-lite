/**
 * 日志告警策略「通知者」邮件搜索：按 id 索引，避免对每个 option 线性扫 userList。
 *
 * 运行：
 * cd web && <tsx> scripts/log-notifier-search-index-test.ts
 */

import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

interface UserItem {
  id: string | number;
  username: string;
  display_name: string;
}

interface NotifierSearchFns {
  buildNotifierUserIndex: (users: UserItem[]) => Map<string, UserItem>;
  matchNotifierUser: (user: UserItem | undefined, input: string) => boolean;
  filterNotifierOption: (
    input: string,
    option: { value?: string | number } | undefined,
    userIndex: Map<string, UserItem>,
  ) => boolean;
}

const here = dirname(fileURLToPath(import.meta.url));
const formPath = resolve(
  here,
  '../src/app/log/(pages)/event/strategy/detail/notificationForm.tsx',
);
const searchPath = resolve(
  here,
  '../src/app/log/(pages)/event/strategy/detail/notifierSearch.ts',
);

function makeUsers(n: number): UserItem[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `u-${i}`,
    username: `user${i}`,
    display_name: `显示${i}`,
  }));
}

function countFindComparisons(n: number): number {
  const users = makeUsers(n);
  let comparisons = 0;
  for (const option of users) {
    users.find((u) => {
      comparisons += 1;
      return u.id === option.id;
    });
  }
  return comparisons;
}

async function loadNotifierSearch(): Promise<NotifierSearchFns> {
  let loaded: Partial<NotifierSearchFns> = {};
  try {
    loaded = await import(
      '../src/app/log/(pages)/event/strategy/detail/notifierSearch.ts'
    );
  } catch {
    // RED：搜索辅助尚未抽出。
  }

  assert.equal(typeof loaded.buildNotifierUserIndex, 'function', '应抽出 buildNotifierUserIndex');
  assert.equal(typeof loaded.matchNotifierUser, 'function', '应抽出 matchNotifierUser');
  assert.equal(typeof loaded.filterNotifierOption, 'function', '应抽出 filterNotifierOption');

  return loaded as NotifierSearchFns;
}

function wrapIndex(
  index: Map<string, UserItem>,
  stats: { lookups: number },
): Map<string, UserItem> {
  return {
    get(id: string) {
      stats.lookups += 1;
      return index.get(id);
    },
  } as Map<string, UserItem>;
}

async function main(): Promise<void> {
  const find20 = countFindComparisons(20);
  const find40 = countFindComparisons(40);
  assert.equal(find20, (20 * 21) / 2, 'find 路径 n=20 比较次数应为 n(n+1)/2');
  assert.equal(find40, (40 * 41) / 2, 'find 路径 n=40 比较次数应为 n(n+1)/2');
  assert.ok(find40 > find20 * 3, 'find 路径比较次数随 n 二次增长');

  const fns = await loadNotifierSearch();
  const users = makeUsers(40);
  const index = fns.buildNotifierUserIndex(users);
  const stats = { lookups: 0 };
  const counted = wrapIndex(index, stats);

  for (const user of users) {
    assert.equal(
      fns.filterNotifierOption('', { value: user.id }, counted),
      true,
      `空搜索应保留用户 ${user.id}`,
    );
  }
  assert.equal(stats.lookups, 40, '索引路径对 n 个 option 只做 n 次按 id 取值');

  const alice: UserItem = {
    id: 'alice-id',
    username: 'alice.wang',
    display_name: 'Alice Display',
  };
  const bob: UserItem = {
    id: 'bob-id',
    username: 'bob.li',
    display_name: '李四',
  };
  const numericAlice: UserItem = {
    id: 17,
    username: 'alice.numeric',
    display_name: 'Numeric Alice',
  };
  const namedIndex = fns.buildNotifierUserIndex([alice, bob, numericAlice]);

  assert.equal(
    fns.filterNotifierOption('alice dis', { value: 'alice-id' }, namedIndex),
    true,
    '应按 display_name 大小写不敏感包含匹配',
  );
  assert.equal(
    fns.filterNotifierOption('WANG', { value: 'alice-id' }, namedIndex),
    true,
    '应按 username 大小写不敏感包含匹配',
  );
  assert.equal(
    fns.filterNotifierOption('bob', { value: 'alice-id' }, namedIndex),
    false,
    '不应误匹配其他用户',
  );
  assert.equal(
    fns.filterNotifierOption('李', { value: 'bob-id' }, namedIndex),
    true,
    'display_name 中文包含应命中',
  );
  assert.equal(
    fns.matchNotifierUser(undefined, 'alice'),
    false,
    '索引未命中时应返回 false',
  );
  assert.equal(
    fns.filterNotifierOption('alice', { value: 'missing' }, namedIndex),
    false,
    '未知 id 不应命中',
  );
  assert.equal(
    fns.filterNotifierOption('numeric alice', { value: 17 }, namedIndex),
    true,
    '数字主键 17 应按 display_name 命中',
  );
  assert.equal(
    fns.filterNotifierOption('numeric alice', { value: '17' }, namedIndex),
    true,
    '字符串 "17" 应按 display_name 命中数字主键用户',
  );
  assert.equal(
    fns.filterNotifierOption('ALICE.NUMERIC', { value: 17 }, namedIndex),
    true,
    '数字主键 17 应按 username 大小写不敏感命中',
  );
  assert.equal(
    fns.filterNotifierOption('alice.numeric', { value: '17' }, namedIndex),
    true,
    '字符串 "17" 应按 username 命中数字主键用户',
  );

  const source = readFileSync(formPath, 'utf8');
  const searchSource = readFileSync(searchPath, 'utf8');
  assert.match(
    searchSource,
    /String\(user\.id\)/,
    'buildNotifierUserIndex 必须用 String(user.id) 规范化索引键',
  );
  assert.doesNotMatch(
    searchSource,
    /\[user\.id,\s*user\]/,
    '不得把未规范化的 user.id 当 Map 键',
  );
  assert.doesNotMatch(
    source,
    /userList\.find/,
    'filterOption 不应再对 userList 做线性 find',
  );
  assert.match(
    source,
    /buildNotifierUserIndex/,
    'NotificationForm 应按 id 建立用户索引',
  );
  assert.match(
    source,
    /filterNotifierOption/,
    'NotificationForm 的 filterOption 应走索引查找',
  );

  console.log('log notifier search index tests passed');
}

void main();
