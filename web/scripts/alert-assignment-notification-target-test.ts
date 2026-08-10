import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  buildNotificationTarget,
  getOrganizationTargetLabels,
  getNotificationTargetFormValue,
} from '../src/app/alarm/(pages)/settings/alertAssign/components/notificationTarget';

assert.deepEqual(getNotificationTargetFormValue(undefined, ['alice']), {
  target_type: 'user',
  personnel: ['alice'],
  organization_ids: [],
  include_children: false,
});

assert.deepEqual(
  getNotificationTargetFormValue(
    {
      type: 'organization',
      organization_ids: [12],
      include_children: true,
    },
    ['legacy-user'],
  ),
  {
    target_type: 'organization',
    personnel: [],
    organization_ids: [12],
    include_children: true,
  },
);

assert.deepEqual(
  getOrganizationTargetLabels(
    [
      {
        id: 1,
        name: '总部',
        subGroups: [{ id: 12, name: '运维中心', subGroups: [] }],
      },
    ],
    [12, 99],
  ),
  ['总部 / 运维中心', '#99'],
);

assert.deepEqual(
  buildNotificationTarget({
    target_type: 'user',
    personnel: ['alice'],
    organization_ids: [12],
    include_children: true,
  }),
  {
    type: 'user',
    usernames: ['alice'],
    organization_ids: [],
    include_children: false,
  },
);

assert.deepEqual(
  buildNotificationTarget({
    target_type: 'organization',
    personnel: ['alice'],
    organization_ids: [12],
    include_children: true,
  }),
  {
    type: 'organization',
    usernames: [],
    organization_ids: [12],
    include_children: true,
  },
);

const groupTreeSelectSource = readFileSync(
  new URL('../src/components/group-tree-select/index.tsx', import.meta.url),
  'utf8',
);
assert.match(
  groupTreeSelectSource,
  /className="rounded shadow-lg bg-\[var\(--color-bg\)\] overflow-hidden"/,
  '组织选择器弹层必须使用不透明语义背景并裁切圆角内容，避免下层表单透出造成错位',
);

console.log('alert assignment notification target validation passed');
