import { expect, it } from 'vitest';
import { createPlatformApiCredential, buildPlatformApiCredential, restorePlatformApiCredential } from '../platformApiCredential';

it.each([
  ['azure', { tenant_id: 'tenant-1', subscription_id: 'sub-1' }],
  ['openstack', { user_domain_name: 'Operations', project_id: 'project-1' }],
  ['nacos', { scheme: 'https' }],
])('%s 创建、编辑和提交保留采集器需要的额外字段', (model, fields) => {
  const raw = { ...createPlatformApiCredential(model), username: 'user', password: 'secret', ...fields };
  expect(buildPlatformApiCredential(model, raw)).toMatchObject(fields);
  expect(restorePlatformApiCredential(model, raw, false)).toMatchObject(fields);
});
