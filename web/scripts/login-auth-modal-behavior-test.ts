import assert from 'node:assert/strict';

import {
  buildLoginAuthBindingPayload,
  resolveLoginAuthProviderKey,
  shouldShowLoginAuthUnmatchedUserAction,
} from '../src/app/system-manager/utils/loginAuthFormUtils';

assert.equal(shouldShowLoginAuthUnmatchedUserAction('wechat'), true);
assert.equal(shouldShowLoginAuthUnmatchedUserAction('feishu'), false);
assert.equal(shouldShowLoginAuthUnmatchedUserAction('bk_lite_builtin'), false);
assert.equal(
  resolveLoginAuthProviderKey(12, [{ id: 12, name: 'WeChat', provider_key: 'wechat', provider_name: 'WeChat' }], {
    id: 1,
    name: 'old',
    integration_instance: 11,
    integration_instance_name: 'Feishu',
    provider_key: 'feishu',
    icon: '',
    description: '',
    order: 1,
    enabled: true,
    external_field: '',
    platform_field: 'email',
    unmatched_user_action: 'deny',
    default_group_name: '',
  }),
  'wechat'
);

assert.deepEqual(
  buildLoginAuthBindingPayload(
    {
      name: '  微信登录  ',
      integration_instance: 12,
      enabled: true,
      icon: 'wechat',
      description: '  desc  ',
      external_field: ' open_id ',
      platform_field: 'email',
      unmatched_user_action: 'create',
      default_group_name: '  默认组  ',
      order: 99,
    },
    'wechat',
  ),
  {
    name: '微信登录',
    integration_instance: 12,
    icon: 'wechat',
    description: '  desc  ',
    external_field: 'open_id',
    platform_field: 'email',
    unmatched_user_action: 'create',
    default_group_name: '默认组',
  }
);

assert.deepEqual(
  buildLoginAuthBindingPayload(
    {
      name: '  飞书登录  ',
      integration_instance: 18,
      enabled: true,
      icon: '',
      description: '  desc  ',
      external_field: ' user_id ',
      platform_field: 'username',
      unmatched_user_action: 'create',
      default_group_name: '  默认组  ',
      order: 7,
    },
    'feishu',
  ),
  {
    name: '飞书登录',
    integration_instance: 18,
    icon: '',
    description: '  desc  ',
    external_field: 'user_id',
    platform_field: 'username',
    unmatched_user_action: 'deny',
    default_group_name: '',
  }
);

console.log('login-auth modal behavior validation passed');
