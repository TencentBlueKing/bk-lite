import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';
import {
  getCredentialDescriptor,
  type CredentialFieldDescriptor,
} from './credentialDescriptors';

export interface CloudCredentialConfig {
  accessKeyLabelKey: string;
  accessSecretLabelKey: string;
  requiresProjectId: boolean;
}

export function getCloudCredentialConfig(modelId: string): CloudCredentialConfig {
  const descriptor = getCredentialDescriptor({ model_id: modelId });
  if (!descriptor || descriptor.formKind !== 'cloud') {
    throw new Error(`未声明云凭据描述：${modelId}`);
  }
  const fields = descriptor.fields as readonly CredentialFieldDescriptor[];
  const accessKey = fields.find((field) => field.key.endsWith('AccessKey'));
  const accessSecret = fields.find(
    (field) => field.key.endsWith('AccessSecret'),
  );
  if (!accessKey?.formLabelKey || !accessSecret?.formLabelKey) {
    throw new Error(`云凭据描述缺少表单标签：${modelId}`);
  }
  return {
    accessKeyLabelKey: accessKey.formLabelKey,
    accessSecretLabelKey: accessSecret.formLabelKey,
    requiresProjectId: fields.some(
      (field) => field.key === 'huaweiProjectId',
    ),
  };
}

export function buildCloudCredential(
  modelId: string,
  raw: CredentialPoolItem,
  region?: Record<string, any>,
) {
  const config = getCloudCredentialConfig(modelId);
  const credential: Record<string, any> = { regions: region };
  if (raw.credential_id) {
    credential.credential_id = raw.credential_id;
  }
  const accessKey = String(raw.accessKey || '').trim();
  const accessSecret = String(raw.accessSecret || '').trim();
  if (accessKey && accessKey !== PASSWORD_PLACEHOLDER) {
    credential.accessKey = accessKey;
  }
  if (accessSecret && accessSecret !== PASSWORD_PLACEHOLDER) {
    credential.accessSecret = accessSecret;
  }
  if (config.requiresProjectId) {
    credential.project_id = String(raw.projectId || '').trim();
  }
  return credential;
}

export function restoreCloudCredential(
  modelId: string,
  raw: Record<string, any> | Record<string, any>[],
  isCopy: boolean,
): CredentialPoolItem {
  const config = getCloudCredentialConfig(modelId);
  const credential = Array.isArray(raw) ? raw[0] || {} : raw;
  const region = credential.regions || {};
  return {
    ...(credential.credential_id
      ? { credential_id: credential.credential_id }
      : {}),
    accessKey: isCopy ? '' : PASSWORD_PLACEHOLDER,
    accessSecret: isCopy ? '' : PASSWORD_PLACEHOLDER,
    regionId: region.resource_id,
    regionName: region.resource_name,
    ...(config.requiresProjectId
      ? { projectId: credential.project_id || '' }
      : {}),
  };
}

export function validateCloudCredential(
  modelId: string,
  raw: CredentialPoolItem,
): 'accessKey' | 'accessSecret' | 'projectId' | 'regionId' | null {
  if (!String(raw.accessKey || '').trim()) {
    return 'accessKey';
  }
  if (!String(raw.accessSecret || '').trim()) {
    return 'accessSecret';
  }
  if (
    getCloudCredentialConfig(modelId).requiresProjectId
    && !String(raw.projectId || '').trim()
  ) {
    return 'projectId';
  }
  if (!raw.regionId) {
    return 'regionId';
  }
  return null;
}

export interface CloudRegionQueryInput {
  modelId: string;
  cloudRegionId: string;
  accessKey?: string;
  accessSecret?: string;
  editId?: number | null;
  host?: string;
  projectId?: string;
}

function isUsableCloudSecret(value?: string) {
  const normalized = String(value || '').trim();
  return Boolean(normalized) && normalized !== PASSWORD_PLACEHOLDER;
}

export function buildCloudRegionQueryParams(input: CloudRegionQueryInput) {
  const accessKey = String(input.accessKey || '').trim();
  const accessSecret = String(input.accessSecret || '').trim();
  const params: Record<string, string | number> = {
    model_id: input.modelId,
    cloud_id: input.cloudRegionId,
  };
  if (input.host) {
    params.host = input.host;
  }
  if (input.projectId) {
    params.project_id = input.projectId;
  }
  if (input.editId) {
    params.task_id = input.editId as number;
  }
  if (isUsableCloudSecret(accessKey) && isUsableCloudSecret(accessSecret)) {
    params.access_key = accessKey;
    params.access_secret = accessSecret;
  }
  return params;
}
