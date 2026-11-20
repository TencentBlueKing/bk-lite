import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  coerceImNotificationTeamIds,
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

const wecomTemplate = {
  matchable_fields: ['userid'],
  receivable_fields: ['userid'],
  default_external_match_field: 'userid',
  default_external_receive_field: 'userid',
};

assert.deepEqual(
  resolveImNotificationFieldPatches({
    editing: false,
    currentMatch: 'email',
    currentReceive: 'user_id',
    template: wecomTemplate,
  }),
  { external_match_field: 'userid', external_receive_field: 'userid' }
);

assert.deepEqual(
  resolveImNotificationFieldPatches({
    editing: true,
    currentMatch: 'email',
    currentReceive: 'user_id',
    template: wecomTemplate,
  }),
  { external_match_field: undefined, external_receive_field: undefined }
);

assert.deepEqual(
  resolveImNotificationFieldPatches({
    editing: false,
    currentMatch: 'email',
    currentReceive: 'user_id',
    template: {
      matchable_fields: ['email', 'user_id'],
      receivable_fields: ['user_id'],
      default_external_match_field: 'email',
      default_external_receive_field: 'user_id',
    },
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

const imModal = readFileSync(
  new URL('../src/app/system-manager/components/channel/im-notification/IMNotificationConfigModal.tsx', import.meta.url),
  'utf8',
);
assert.match(imModal, /dropdownRender/);
assert.match(imModal, /function AccountAssociationField/);
assert.doesNotMatch(imModal, /AccountAssociationSelect/);
assert.match(imModal, /name="account_association"/);
assert.match(imModal, /required: true/);
const instanceAt = imModal.indexOf('name="integration_instance"');
const associationAt = imModal.indexOf('name="account_association"');
const teamAt = imModal.indexOf('name="team"');
assert.ok(instanceAt >= 0 && associationAt > instanceAt && teamAt > associationAt);
const channelModal = readFileSync(
  new URL('../src/app/system-manager/components/channel/channelModal.tsx', import.meta.url),
  'utf8',
);
const skillChannelPage = readFileSync(
  new URL('../src/app/opspilot/(pages)/skill/detail/channel/page.tsx', import.meta.url),
  'utf8',
);
assert.match(channelModal, /function AccountAssociationField/);
assert.match(channelModal, /dropdownRender/);
assert.doesNotMatch(channelModal, /AccountAssociationSelect/);
assert.match(skillChannelPage, /function AccountAssociationField/);
assert.match(skillChannelPage, /dropdownRender/);
assert.doesNotMatch(skillChannelPage, /@\/app\/system-manager\/components/);
assert.match(imModal, /accountAssociationTooltip/);
assert.match(imModal, /GroupTreeSelect/);
assert.match(imModal, /name="team"/);
assert.match(imModal, /common\.organization/);
const imPage = readFileSync(
  new URL('../src/app/system-manager/(pages)/channel/im-notification/page.tsx', import.meta.url),
  'utf8',
);
const associationPanel = readFileSync(
  new URL('../src/app/system-manager/components/user/user-sync/AccountAssociationPanel.tsx', import.meta.url),
  'utf8',
);
assert.match(associationPanel, /resolveExternalFieldOptionLabel/);
assert.match(associationPanel, /resolveImNotificationFieldPatches/);
assert.doesNotMatch(associationPanel, /external_receive_field: 'user_id'/);
assert.doesNotMatch(imPage, /externalFieldOption\.\$\{field\}/);
assert.match(imPage, /coerceImNotificationTeamIds/);
assert.match(imPage, /<Space wrap className="max-w-full">/);
assert.deepEqual(coerceImNotificationTeamIds(['1', '', 0, 2, 'abc']), [1, 2]);
assert.deepEqual(coerceImNotificationTeamIds(undefined), []);
const zh = JSON.parse(
  readFileSync(new URL('../src/app/system-manager/locales/zh.json', import.meta.url), 'utf8'),
);
assert.equal(zh.system.channel.imNotificationPage.externalFieldOption, undefined);

console.log('im-notification edit form validation passed');
