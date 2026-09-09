import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLatestRequestGuard } from '../src/context/latestRequestGuard.ts';

interface ClusterSetting {
  instanceId: string;
  host_log_path: string;
  namespace_patterns: string;
  pod_patterns: string;
  unknown?: boolean;
}

interface FormState {
  accessType: 'new' | 'existing';
  k8sCluster: string | undefined;
  host_log_path: string | undefined;
  namespace_patterns: string | undefined;
  pod_patterns: string | undefined;
  settingUnknown: boolean;
}

interface InFlightRead {
  requestId: number;
  instanceId: string;
  apply: (setting: ClusterSetting) => boolean;
}

const here = dirname(fileURLToPath(import.meta.url));
const accessConfigPath = resolve(
  here,
  '../src/app/log/(pages)/integration/list/detail/configure/k8s/accessConfig.tsx',
);

const settingA: ClusterSetting = {
  instanceId: 'cluster-a',
  host_log_path: '/var/log/a',
  namespace_patterns: 'ns-a',
  pod_patterns: 'pod-a',
};

const settingB: ClusterSetting = {
  instanceId: 'cluster-b',
  host_log_path: '/var/log/b',
  namespace_patterns: 'ns-b',
  pod_patterns: 'pod-b',
};

function createAccessSession() {
  const guard = createLatestRequestGuard();
  let form: FormState = {
    accessType: 'existing',
    k8sCluster: undefined,
    host_log_path: undefined,
    namespace_patterns: undefined,
    pod_patterns: undefined,
    settingUnknown: false,
  };

  const applyIfCurrent = (requestId: number, instanceId: string, setting: ClusterSetting) => {
    return guard.commitIfCurrent(requestId, () => {
      if (form.accessType !== 'existing' || form.k8sCluster !== instanceId) {
        return;
      }
      if (setting.unknown) {
        form = {
          ...form,
          settingUnknown: true,
          host_log_path: undefined,
          namespace_patterns: undefined,
          pod_patterns: undefined,
        };
        return;
      }
      form = {
        ...form,
        settingUnknown: false,
        host_log_path: setting.host_log_path,
        namespace_patterns: setting.namespace_patterns,
        pod_patterns: setting.pod_patterns,
      };
    });
  };

  const loadSetting = (instanceId: string): InFlightRead => {
    const requestId = guard.begin();
    return {
      requestId,
      instanceId,
      apply: (setting) => applyIfCurrent(requestId, instanceId, setting),
    };
  };

  const selectCluster = (instanceId: string): InFlightRead => {
    guard.invalidate();
    form = { ...form, accessType: 'existing', k8sCluster: instanceId };
    return loadSetting(instanceId);
  };

  const switchToNew = () => {
    guard.invalidate();
    form = { ...form, accessType: 'new', settingUnknown: false };
  };

  const unmount = () => {
    guard.invalidate();
  };

  return {
    getForm: () => form,
    selectCluster,
    pointCluster: (instanceId: string) => {
      form = { ...form, accessType: 'existing', k8sCluster: instanceId };
    },
    switchToNew,
    unmount,
    submitInstanceId: () => form.k8sCluster,
  };
}

function assertAccessConfigUsesGuard(source: string) {
  assert.match(
    source,
    /from ['"]@\/context\/latestRequestGuard['"]/,
    'loadSetting 必须复用 @/context/latestRequestGuard，不得复制新 guard',
  );
  assert.match(source, /createLatestRequestGuard/, 'AccessConfig 必须创建 latest request guard');
  assert.match(
    source,
    /requestGuard\.begin\(\)/,
    'loadSetting 必须按单调序号 begin',
  );
  assert.match(
    source,
    /requestGuard\.commitIfCurrent\(/,
    'loadSetting 只能经 commitIfCurrent 回填表单',
  );
  assert.match(
    source,
    /requestGuard\.commitIfCurrent\([\s\S]*setFieldsValue/,
    '只有当前请求才允许 setFieldsValue',
  );
  assert.match(
    source,
    /requestGuard\.invalidate\(\)/,
    '切换集群、新建资产或卸载必须 invalidate 在途回读',
  );
  assert.match(
    source,
    /event\.target\.value === 'new'[\s\S]*requestGuard\.invalidate\(\)/,
    '切到新建资产必须作废在途回读',
  );
  assert.match(
    source,
    /return\s*\(\)\s*=>\s*requestGuard\.invalidate\(\)/,
    '卸载必须作废在途回读',
  );
  assert.match(
    source,
    /onChange=\{\(value\)\s*=>[\s\S]*requestGuard\.invalidate\(\)/,
    '切换集群必须 invalidate',
  );
  assert.match(
    source,
    /getFieldValue\(['"]k8sCluster['"]\)/,
    '当前集群只接受匹配 instance 的最新响应',
  );
  assert.match(
    source,
    /let instanceId = values\.k8sCluster as string/,
    'handleSubmit 仍须用当前 k8sCluster 作为保存目标',
  );
  assert.match(
    source,
    /saveK8sCollectSetting\(\{[\s\S]*instance_id: instanceId/,
    '保存 payload 的 instance_id 必须来自当前选中集群',
  );
  assert.match(source, /setting\?\.unknown/, '不得改 unknown 配置引导');
  assert.match(source, /getK8sCollectSetting\(instanceId\)/, '不得改 GET 入参');
  assert.doesNotMatch(
    source,
    /await getK8sCollectSetting\([^)]*\);\s*(?:if \(setting\?\.unknown\)|setSettingUnknown|form\.setFieldsValue)/,
    'loadSetting 不得在 await 后无条件回填',
  );
  assert.doesNotMatch(
    source,
    /function createLatestRequestGuard|const createLatestRequestGuard\s*=/,
    '不得在 AccessConfig 内复制一套序号 guard',
  );
}

async function main() {
  const race = createAccessSession();
  const staleA = race.selectCluster(settingA.instanceId);
  const latestB = race.selectCluster(settingB.instanceId);
  assert.equal(race.submitInstanceId(), 'cluster-b', '切换后保存目标必须是当前 k8sCluster');
  assert.equal(latestB.apply(settingB), true, '当前集群的最新响应必须回填');
  assert.equal(staleA.apply(settingA), false, '先 B 后 A 的完成顺序不得回填 A');
  assert.equal(race.getForm().host_log_path, '/var/log/b', '迟到的 A 路径不得覆盖 B');
  assert.equal(race.getForm().namespace_patterns, 'ns-b');
  assert.equal(race.getForm().pod_patterns, 'pod-b');
  assert.equal(race.getForm().k8sCluster, 'cluster-b');
  assert.equal(race.submitInstanceId(), 'cluster-b', 'handleSubmit 仍用当前 k8sCluster');

  const mismatched = createAccessSession();
  const readA = mismatched.selectCluster(settingA.instanceId);
  mismatched.pointCluster(settingB.instanceId);
  assert.equal(readA.apply(settingA), true, '序号仍当前时回调会执行');
  assert.equal(
    mismatched.getForm().host_log_path,
    undefined,
    '当前集群不得接受不匹配 instance 的响应字段',
  );
  assert.equal(mismatched.submitInstanceId(), 'cluster-b');

  const switchedToNew = createAccessSession();
  const inflightNew = switchedToNew.selectCluster(settingA.instanceId);
  switchedToNew.switchToNew();
  assert.equal(inflightNew.apply(settingA), false, '切到新建资产必须作废在途回读');
  assert.equal(switchedToNew.getForm().host_log_path, undefined);
  assert.equal(switchedToNew.getForm().accessType, 'new');

  const unmounted = createAccessSession();
  const inflightUnmount = unmounted.selectCluster(settingA.instanceId);
  unmounted.unmount();
  assert.equal(inflightUnmount.apply(settingA), false, '卸载必须作废在途回读');
  assert.equal(unmounted.getForm().host_log_path, undefined);

  const unknownLatest = createAccessSession();
  const staleKnown = unknownLatest.selectCluster(settingA.instanceId);
  const latestUnknown = unknownLatest.selectCluster(settingB.instanceId);
  assert.equal(
    latestUnknown.apply({ ...settingB, unknown: true }),
    true,
    '当前集群的 unknown 引导仍可回填',
  );
  assert.equal(staleKnown.apply(settingA), false, '迟到的已知配置不得覆盖 unknown 引导');
  assert.equal(unknownLatest.getForm().settingUnknown, true);
  assert.equal(unknownLatest.getForm().host_log_path, undefined);

  const source = readFileSync(accessConfigPath, 'utf8');
  assertAccessConfigUsesGuard(source);

  console.log('log k8s access setting race test passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
