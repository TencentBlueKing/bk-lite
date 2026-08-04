import assert from 'node:assert/strict';

import {
  getImNotificationUnavailableEditingInstance,
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

console.log('im-notification edit form validation passed');
