import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  createK3sAccessListLoad,
  shouldReloadK3sAccessList,
  type K3sAccessListLoad,
  type K3sAccessListLoadDeps,
} from '../src/app/monitor/(pages)/integration/list/detail/configure/k3s/k3sAccessListLoad.ts';

const here = dirname(fileURLToPath(import.meta.url));
const accessConfigPath = resolve(
  here,
  '../src/app/monitor/(pages)/integration/list/detail/configure/k3s/accessConfig.tsx',
);
const localePath = resolve(here, '../src/app/monitor/locales/zh.json');
const commonLocalePath = resolve(here, '../src/locales/zh.json');

const REPRO_COPY = {
  menu: '集成',
  buttons: ['接入', '下一步'],
  step: 'K3S 接入配置',
  radios: ['新建 K3S 集群', '选择已有 K3S 集群'],
  fields: ['K3S 集群名称', '所属组织', 'K3S 集群', '云区域'],
} as const;

interface ListRequestCounts {
  cloudRegion: number;
  instance: number;
}

function makeFn(label: string): () => typeof label {
  return () => label;
}

function simulateStayOnFirstStep(
  loader: K3sAccessListLoad,
  renders: K3sAccessListLoadDeps[]
): ListRequestCounts {
  const counts: ListRequestCounts = { cloudRegion: 0, instance: 0 };
  let previous: K3sAccessListLoadDeps | null = null;
  let clusters: unknown[] = [];

  for (const next of renders) {
    if (!shouldReloadK3sAccessList(previous, next)) {
      previous = next;
      continue;
    }

    const ticket = loader.begin(next.objectId);
    counts.cloudRegion += 1;
    counts.instance += 1;
    const nextClusters: unknown[] = [];
    if (loader.shouldApply(ticket)) {
      clusters = nextClusters;
    }
    previous = {
      ...next,
      getInstanceList: makeFn(`clusters-setter-${clusters.length}`),
    };
  }

  return counts;
}

function assertReproCopy() {
  const monitorLocale = JSON.parse(readFileSync(localePath, 'utf8')) as {
    monitor: {
      integrations: {
        integration: string;
        access: string;
        k3s: {
          accessConfig: string;
          newAsset: string;
          existingAsset: string;
          clusterName: string;
          organization: string;
          k3sCluster: string;
          cloudRegion: string;
        };
      };
    };
  };
  const commonLocale = JSON.parse(readFileSync(commonLocalePath, 'utf8')) as {
    common: { next: string };
  };
  const k3s = monitorLocale.monitor.integrations.k3s;

  assert.equal(monitorLocale.monitor.integrations.integration, REPRO_COPY.menu);
  assert.equal(monitorLocale.monitor.integrations.access, REPRO_COPY.buttons[0]);
  assert.equal(commonLocale.common.next, REPRO_COPY.buttons[1]);
  assert.equal(k3s.accessConfig, REPRO_COPY.step);
  assert.equal(k3s.newAsset, REPRO_COPY.radios[0]);
  assert.equal(k3s.existingAsset, REPRO_COPY.radios[1]);
  assert.equal(k3s.clusterName, REPRO_COPY.fields[0]);
  assert.equal(k3s.organization, REPRO_COPY.fields[1]);
  assert.equal(k3s.k3sCluster, REPRO_COPY.fields[2]);
  assert.equal(k3s.cloudRegion, REPRO_COPY.fields[3]);
}

function assertAccessConfigUsesObjectIdLoad(source: string) {
  assert.match(
    source,
    /from ['"]\.\/k3sAccessListLoad['"]/,
    'AccessConfig 必须复用抽出的 k3sAccessListLoad'
  );
  assert.match(source, /createK3sAccessListLoad/, 'AccessConfig 必须创建列表加载世代');
  assert.match(source, /\.begin\(/, 'AccessConfig 必须 begin 当前 objectId 加载');
  assert.match(source, /\.shouldApply\(/, 'AccessConfig 必须用 shouldApply 忽略过期响应');
  assert.match(source, /\.invalidate\(/, 'AccessConfig 必须在卸载或 objectId 变化时作废在途响应');
  assert.match(
    source,
    /getInstanceListRef/,
    'AccessConfig 必须把 getInstanceList 放进 ref，避免函数身份进入 effect'
  );
  assert.match(
    source,
    /getCloudRegionListRef/,
    'AccessConfig 必须把 getCloudRegionList 放进 ref'
  );
  assert.doesNotMatch(
    source,
    /\[getCloudRegionList, getInstanceList, objectId\]/,
    'effect 不得继续依赖不稳定的 API 函数身份'
  );
  assert.match(
    source,
    /page_size:\s*-1/,
    '不得改实例/云区域列表的 page_size=-1'
  );
}

function main() {
  assertReproCopy();

  const getCloudRegionList = makeFn('cloud-region');
  const firstGetInstanceList = makeFn('instance-a');
  const secondGetInstanceList = makeFn('instance-b');
  assert.notEqual(
    firstGetInstanceList,
    secondGetInstanceList,
    '两次 render 的 getInstanceList 必须是不同函数身份'
  );

  const stayLoader = createK3sAccessListLoad();
  const stayCounts = simulateStayOnFirstStep(stayLoader, [
    { objectId: 42, getCloudRegionList, getInstanceList: firstGetInstanceList },
    { objectId: 42, getCloudRegionList, getInstanceList: secondGetInstanceList },
    { objectId: 42, getCloudRegionList, getInstanceList: makeFn('instance-c') },
  ]);

  assert.equal(
    stayCounts.cloudRegion,
    1,
    'objectId 不变时，getInstanceList 身份变化 + setClusters 新数组不得继续请求云区域'
  );
  assert.equal(
    stayCounts.instance,
    1,
    'objectId 不变时，getInstanceList 身份变化 + setClusters 新数组不得继续请求实例列表'
  );
  assert.equal(
    shouldReloadK3sAccessList(
      { objectId: 42, getCloudRegionList, getInstanceList: firstGetInstanceList },
      { objectId: 42, getCloudRegionList, getInstanceList: secondGetInstanceList }
    ),
    false,
    '同一 objectId 不得因函数身份重载'
  );

  const switchLoader = createK3sAccessListLoad();
  const switchCounts = simulateStayOnFirstStep(switchLoader, [
    { objectId: 42, getCloudRegionList, getInstanceList: firstGetInstanceList },
    { objectId: 99, getCloudRegionList, getInstanceList: firstGetInstanceList },
  ]);
  assert.deepEqual(
    switchCounts,
    { cloudRegion: 2, instance: 2 },
    'objectId 变化必须重新加载云区域和实例列表'
  );

  const staleLoader = createK3sAccessListLoad();
  const firstTicket = staleLoader.begin(42);
  staleLoader.invalidate();
  const secondTicket = staleLoader.begin(99);
  assert.equal(staleLoader.shouldApply(firstTicket), false, '过期世代必须忽略');
  assert.equal(staleLoader.shouldApply(secondTicket), true, '最新世代可以写回');

  const accessConfigSource = readFileSync(accessConfigPath, 'utf8');
  assertAccessConfigUsesObjectIdLoad(accessConfigSource);

  console.log('monitor-k3s-access-list-loop-test: ok');
}

main();
