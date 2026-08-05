import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  buildCloudCredential,
  getCloudCredentialConfig,
  restoreCloudCredential,
  validateCloudCredential,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/cloudCredentialConfig';

assert.deepEqual(getCloudCredentialConfig('aliyun_account'), {
  accessKeyLabelKey: 'Collection.cloudTask.aliyunAccessKeyId',
  accessSecretLabelKey: 'Collection.cloudTask.aliyunAccessKeySecret',
  requiresProjectId: false,
});
assert.deepEqual(getCloudCredentialConfig('qcloud'), {
  accessKeyLabelKey: 'Collection.cloudTask.tencentSecretId',
  accessSecretLabelKey: 'Collection.cloudTask.tencentSecretKey',
  requiresProjectId: false,
});
assert.deepEqual(getCloudCredentialConfig('hwcloud'), {
  accessKeyLabelKey: 'Collection.cloudTask.huaweiAk',
  accessSecretLabelKey: 'Collection.cloudTask.huaweiSk',
  requiresProjectId: true,
});

const region = { resource_id: 'cn-north-4', resource_name: '华北四' };
assert.deepEqual(
  buildCloudCredential(
    'hwcloud',
    {
      accessKey: 'AK',
      accessSecret: 'SK',
      projectId: 'project-123',
      regionId: 'cn-north-4',
    },
    region,
  ),
  {
    accessKey: 'AK',
    accessSecret: 'SK',
    project_id: 'project-123',
    regions: region,
  },
);
assert.equal(
  validateCloudCredential('hwcloud', {
    accessKey: 'AK',
    accessSecret: 'SK',
    projectId: '',
    regionId: 'cn-north-4',
  }),
  'projectId',
);
assert.equal(
  validateCloudCredential('qcloud', {
    accessKey: 'SID',
    accessSecret: 'SKEY',
    regionId: 'ap-guangzhou',
  }),
  null,
);
assert.equal(
  restoreCloudCredential(
    'hwcloud',
    [{
      credential_id: 'cred-hwcloud',
      accessKey: '******',
      accessSecret: '******',
      project_id: 'project-123',
      regions: region,
    }],
    false,
  ).projectId,
  'project-123',
);
assert.deepEqual(
  restoreCloudCredential(
    'qcloud',
    [{
      credential_id: 'cred-qcloud',
      accessKey: '******',
      accessSecret: '******',
      regions: { resource_id: 'ap-guangzhou', resource_name: '广州' },
    }],
    true,
  ),
  {
    credential_id: 'cred-qcloud',
    accessKey: '',
    accessSecret: '',
    regionId: 'ap-guangzhou',
    regionName: '广州',
  },
);

const taskSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/cloudTask.tsx',
  ),
  'utf8',
);
assert.match(taskSource, /getCloudCredentialConfig/);
assert.match(taskSource, /projectId/);
assert.match(taskSource, /cloudCredentialLabels/);

const editorSource = readFileSync(
  resolve(
    process.cwd(),
    'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx',
  ),
  'utf8',
);
assert.match(
  editorSource,
  /aria-label=\{t\('common\.refresh'\)\}[\s\S]*?icon=\{<SyncOutlined[\s\S]*?aria-hidden/,
  '云区域刷新图标按钮应有可访问名称，装饰图标应对辅助技术隐藏',
);

console.log('CMDB cloud credential contract passed');
