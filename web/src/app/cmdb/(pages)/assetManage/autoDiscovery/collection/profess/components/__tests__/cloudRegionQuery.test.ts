import { describe, expect, it } from 'vitest';

import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import {
  buildCloudCredential,
  buildCloudRegionQueryParams,
} from '../cloudCredentialConfig';

describe('buildCloudRegionQueryParams', () => {
  it('reuses the saved task instead of sending masked secrets when editing', () => {
    expect(buildCloudRegionQueryParams({
      modelId: 'qcloud',
      cloudRegionId: 'fusion-collector-default',
      accessKey: PASSWORD_PLACEHOLDER,
      accessSecret: PASSWORD_PLACEHOLDER,
      editId: 42,
    })).toEqual({
      model_id: 'qcloud',
      cloud_id: 'fusion-collector-default',
      task_id: 42,
    });
  });

  it('does the same for Aliyun edit', () => {
    expect(buildCloudRegionQueryParams({
      modelId: 'aliyun_account',
      cloudRegionId: 'fusion-collector-default',
      accessKey: PASSWORD_PLACEHOLDER,
      accessSecret: PASSWORD_PLACEHOLDER,
      editId: 7,
      host: 'ecs.aliyuncs.com',
    })).toEqual({
      model_id: 'aliyun_account',
      cloud_id: 'fusion-collector-default',
      task_id: 7,
      host: 'ecs.aliyuncs.com',
    });
  });

  it('sends plaintext keys only when creating or replacing credentials', () => {
    expect(buildCloudRegionQueryParams({
      modelId: 'qcloud',
      cloudRegionId: 'fusion-collector-default',
      accessKey: 'AKIDnew',
      accessSecret: 'sk-new',
    })).toEqual({
      model_id: 'qcloud',
      cloud_id: 'fusion-collector-default',
      access_key: 'AKIDnew',
      access_secret: 'sk-new',
    });
  });

  it('uses the edited page secrets instead of the saved task when the user changes them', () => {
    expect(buildCloudRegionQueryParams({
      modelId: 'qcloud',
      cloudRegionId: 'fusion-collector-default',
      accessKey: 'AKIDchanged',
      accessSecret: 'sk-changed',
      editId: 42,
    })).toEqual({
      model_id: 'qcloud',
      cloud_id: 'fusion-collector-default',
      task_id: 42,
      access_key: 'AKIDchanged',
      access_secret: 'sk-changed',
    });
  });

  it('still reuses the saved task when edit inputs were cleared back to empty', () => {
    expect(buildCloudRegionQueryParams({
      modelId: 'qcloud',
      cloudRegionId: 'fusion-collector-default',
      accessKey: '',
      accessSecret: '',
      editId: 42,
    })).toEqual({
      model_id: 'qcloud',
      cloud_id: 'fusion-collector-default',
      task_id: 42,
    });
  });
});

describe('buildCloudCredential', () => {
  it('keeps credential_id when the page secrets are still masked', () => {
    expect(buildCloudCredential('qcloud', {
      credential_id: 'cred-qcloud',
      accessKey: PASSWORD_PLACEHOLDER,
      accessSecret: PASSWORD_PLACEHOLDER,
    }, { resource_id: 'ap-guangzhou' })).toEqual({
      credential_id: 'cred-qcloud',
      regions: { resource_id: 'ap-guangzhou' },
    });
  });
});
