import assert from 'node:assert/strict';

import { resolveImNotificationFieldPatches } from '../src/app/system-manager/utils/imNotificationUtils';

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

console.log('im-notification edit form validation passed');
