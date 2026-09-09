import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  getImNotificationUnavailableEditingInstance,
  resolveExternalFieldOptionLabel,
  resolveImNotificationFieldPatches,
} from '../src/app/system-manager/utils/imNotificationUtils';

const editRecord = {
  external_match_field: 'email',
  external_receive_field: 'user_id',
};

assert.deepEqual(
  resolveImNotificationFieldPatches({
    editing: true,
    currentMatch: editRecord.external_match_field,
    currentReceive: editRecord.external_receive_field,
    template: null,
  }),
  {}
);

assert.deepEqual(
  getImNotificationUnavailableEditingInstance(
    [{ id: 9, name: 'WeCom', provider_key: 'wecom', provider_name: 'WeCom' }],
    {
      integration_instance: 2,
      integration_instance_name: 'Feishu IM',
      provider_key: 'feishu',
    },
  ),
  { id: 2, name: 'Feishu IM', provider_key: 'feishu', provider_name: '' },
);
assert.equal(
  getImNotificationUnavailableEditingInstance(
    [{ id: 2, name: 'Feishu IM', provider_key: 'feishu', provider_name: 'Feishu' }],
    {
      integration_instance: 2,
      integration_instance_name: 'Feishu IM',
      provider_key: 'feishu',
    },
  ),
  null,
);

assert.equal(resolveExternalFieldOptionLabel('id', { id: 'Graph 用户 ID' }), 'Graph 用户 ID');
assert.equal(resolveExternalFieldOptionLabel('mail', {}), 'mail');
assert.equal(resolveExternalFieldOptionLabel('userPrincipalName'), 'userPrincipalName');

const imPage = readFileSync(
  new URL('../src/app/system-manager/(pages)/channel/im-notification/page.tsx', import.meta.url),
  'utf8',
);
assert.match(imPage, /resolveExternalFieldOptionLabel/);
assert.doesNotMatch(imPage, /externalFieldOption\.\$\{field\}/);
const zh = JSON.parse(
  readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'),
);
assert.equal(zh.system.channel.imNotificationPage.externalFieldOption, undefined);

console.log('im-notification edit form validation passed');
