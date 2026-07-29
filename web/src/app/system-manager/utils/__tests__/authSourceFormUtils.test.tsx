import { describe, expect, it } from 'vitest';
import type { AuthSource } from '../../types/security';
import {
  buildUpdatePayload,
  mergeAuthSourceUpdate,
  populateFormFromSource,
  type WeChatFormValues,
} from '../authSourceFormUtils';

const existingSource: AuthSource = {
  id: 1,
  name: '企业微信',
  source_type: 'wechat',
  app_id: 'wx-app-id',
  app_secret: 'ENCRYPTED_CIPHER',
  other_config: {
    redirect_uri: 'https://example.com/callback',
    callback_url: 'https://example.com/callback',
  },
  enabled: true,
  is_build_in: false,
};

const formValues: WeChatFormValues = {
  name: '企业微信',
  app_id: 'wx-app-id',
  app_secret: '',
  enabled: true,
  redirect_uri: 'https://example.com/callback',
  callback_url: 'https://example.com/callback',
};

describe('认证源密钥编辑契约', () => {
  it('编辑表单不回填响应中的历史密钥', () => {
    const populated = populateFormFromSource(existingSource);

    expect(populated).not.toHaveProperty('app_secret');
  });

  it('未输入新密钥时更新 payload 不发送 app_secret', () => {
    const payload = buildUpdatePayload('wechat', formValues, []);

    expect(payload).not.toHaveProperty('app_secret');
  });

  it('输入新密钥时更新 payload 显式发送 app_secret', () => {
    const payload = buildUpdatePayload(
      'wechat',
      { ...formValues, app_secret: 'new-secret' },
      []
    );

    expect(payload.app_secret).toBe('new-secret');
  });

  it('保存成功后不把新旧 app_secret 合并回前端列表状态', () => {
    const merged = mergeAuthSourceUpdate(existingSource, {
      name: '新名称',
      app_secret: 'new-secret',
    });

    expect(merged.name).toBe('新名称');
    expect(merged).not.toHaveProperty('app_secret');
  });
});
