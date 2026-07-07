import assert from 'node:assert/strict';

import {
  buildLoginAuthBindingPayload,
  resolveLoginAuthDefaultIcon,
  resolveLoginAuthDefaultExternalField,
  resolveLoginAuthProviderKey,
  resolveLoginAuthTemplate,
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
assert.equal(resolveLoginAuthDefaultIcon('feishu'), 'feishu');
assert.equal(resolveLoginAuthDefaultIcon('wechat'), 'wechat');
assert.equal(resolveLoginAuthDefaultIcon('unknown'), '');
assert.equal(
  resolveLoginAuthDefaultExternalField({
    title: 'Login Auth',
    groups: [],
    available_external_fields: ['user_id', 'open_id'],
    matchable_fields: [],
    receivable_fields: [],
    default_external_match_field: 'user_id',
    default_external_receive_field: '',
  }),
  'user_id'
);
assert.equal(
  resolveLoginAuthDefaultExternalField({
    title: 'Login Auth',
    groups: [],
    available_external_fields: ['open_id', 'unionid'],
    matchable_fields: [],
    receivable_fields: [],
    default_external_match_field: '',
    default_external_receive_field: '',
  }),
  'open_id'
);
assert.equal(resolveLoginAuthDefaultExternalField(null), '');
assert.deepEqual(
  resolveLoginAuthTemplate(
    18,
    [{ id: 18, name: 'Feishu SSO', provider_key: 'feishu', provider_name: 'Feishu' }],
    [{
      key: 'feishu',
      name: 'Feishu',
      description: '',
      instance_template: [],
      instance_templates: {},
      business_templates: {
        login_auth_form: {
          title: 'Login Auth',
          groups: [],
          available_external_fields: ['user_id', 'open_id'],
          matchable_fields: [],
          receivable_fields: [],
          default_external_match_field: 'user_id',
          default_external_receive_field: '',
        },
      },
      capabilities: [{
        key: 'login_auth',
        name: 'Login Auth',
        description: '',
        connection_template: [],
        business_template: 'login_auth_form',
      }],
    }],
  ),
  {
    title: 'Login Auth',
    groups: [],
    available_external_fields: ['user_id', 'open_id'],
    matchable_fields: [],
    receivable_fields: [],
    default_external_match_field: 'user_id',
    default_external_receive_field: '',
  }
);

assert.deepEqual(
  buildLoginAuthBindingPayload(
    {
      name: '  微信登录  ',
      integration_instance: 12,
      enabled: true,
      icon: 'wechat',
      description: '  desc  ',
      external_field: ' openid ',
      platform_field: 'email',
      unmatched_user_action: 'create',
      default_group_name: '',
      order: 99,
    },
    'wechat',
  ),
  {
    name: '微信登录',
    integration_instance: 12,
    icon: 'wechat',
    description: '  desc  ',
    external_field: 'openid',
    platform_field: 'email',
    unmatched_user_action: 'create',
    default_group_name: '',
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

// WeChat manifest 现在默认外部字段为 openid(无下划线)
assert.equal(
  resolveLoginAuthDefaultExternalField({
    title: 'Login Auth',
    groups: [],
    available_external_fields: ['openid', 'unionid'],
    matchable_fields: [],
    receivable_fields: [],
    default_external_match_field: 'openid',
    default_external_receive_field: '',
  }),
  'openid'
);

console.log('login-auth modal behavior validation passed');
