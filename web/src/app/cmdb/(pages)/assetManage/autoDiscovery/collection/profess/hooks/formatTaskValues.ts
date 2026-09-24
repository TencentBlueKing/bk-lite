import { ENTER_TYPE, PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import { CredentialPoolItem, TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { BaseTaskRef } from '../components/baseTask';
import { isVaultAuthField } from '../utils/vaultAuthFields';

interface FormatTaskValuesOptions {
  values: any;
  baseRef: React.RefObject<BaseTaskRef>;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  modelId: string;
  formatCycleValue: (values: any) => any;
}

interface CredentialConfig {
  [key: string]: string | ((value: any) => any);
}

export const trimFormString = (value: any) =>
  typeof value === 'string' ? value.trim() : value;

/**
 * 格式化任务表单的公共字段
 * 只处理所有任务类型都有的字段，实例相关逻辑由各任务自行处理
 */
export const formatTaskValues = ({
  values,
  baseRef,
  modelItem,
  modelId,
  formatCycleValue,
}: FormatTaskValuesOptions) => {
  const driverType = modelItem.type;

  const accessPoint = baseRef.current?.accessPoints.find(
    (item: any) => item.value === values.accessPointId
  );

  return {
    name: values.taskName,
    input_method: values.enterType === ENTER_TYPE.APPROVAL ? 1 : 0,
    timeout: values.timeout || 60,
    scan_cycle: formatCycleValue(values),
    access_point: accessPoint?.origin && [accessPoint.origin],
    model_id: modelId,
    task_type: modelItem.task_type,
    driver_type: driverType,
    accessPointId: values.access_point?.[0]?.id,
    team: values.organization || [],
    data_cleanup_strategy: values.cleanupStrategy,
    expire_days:
      values.cleanupStrategy === 'after_expiration'
        ? (values.cleanupDays ?? 0)
        : 0,
    params: {
      ip_precheck: Boolean(values.ip_precheck),
    },
  };
};

/**
 * 构建凭据对象，自动处理密码占位符
 * @param credentialMap 凭据字段映射，key为目标字段名，value为源字段名或处理函数
 * @param values 表单值
 * @returns 处理后的凭据对象
 */
export const buildCredential = (
  credentialMap: CredentialConfig,
  values: any
): Record<string, any> => {
  const credential: Record<string, any> = {};

  Object.entries(credentialMap).forEach(([targetKey, sourceConfig]) => {
    if (typeof sourceConfig === 'function') {
      const result = trimFormString(sourceConfig(values));
      if (result !== undefined) {
        credential[targetKey] = result;
      }
    } else {
      const value = trimFormString(values[sourceConfig]);

      if (value && value !== PASSWORD_PLACEHOLDER) {
        credential[targetKey] = value;
      } else if (value !== PASSWORD_PLACEHOLDER && value !== undefined) {
        credential[targetKey] = value;
      }
    }
  });

  return credential;
};

export const normalizeCredentialPool = (
  rawCredential: CredentialPoolItem | CredentialPoolItem[] | null | undefined
): CredentialPoolItem[] => {
  if (!rawCredential) {
    return [];
  }

  if (Array.isArray(rawCredential)) {
    return rawCredential.map((item) => ({ ...item }));
  }

  return [{ ...rawCredential }];
};

/** 表单字段映射后仍保留任务来源、仓库 ID 和类型选择。 */
export const withTaskCredentialSource = (
  raw: CredentialPoolItem,
  built: CredentialPoolItem,
): CredentialPoolItem => {
  const result = { ...(raw.credential_id ? { credential_id: raw.credential_id } : {}), ...built, credential_source: raw.credential_source || 'inline' };
  if (result.credential_source === 'vault') {
    Object.keys(result).forEach((field) => {
      if (isVaultAuthField(field, raw)) delete result[field];
    });
    result.vault_credential_id = raw.vault_credential_id;
    result.vault_type_key = raw.vault_type_key;
    for (const field of ['source', 'user_type', 'login_type', 'loginType', 'encrypt', 'api_url', 'scheme', 'project_id', 'subscription_id', 'api_version']) {
      if (result[field] === undefined && raw[field] !== undefined) result[field] = raw[field];
    }
  }
  return result;
};

export const buildCredentialPool = (
  rawItems: CredentialPoolItem[] = [],
  normalizeItem: (item: CredentialPoolItem, index: number) => CredentialPoolItem
): CredentialPoolItem[] => {
  return rawItems
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => {
      const normalized: CredentialPoolItem = { ...(item.credential_id ? { credential_id: item.credential_id } : {}), ...normalizeItem(item, index) };
      const source = item.credential_source || 'inline';
      normalized.credential_source = source;
      if (source === 'vault') {
        normalized.vault_credential_id = item.vault_credential_id;
        normalized.vault_type_key = item.vault_type_key;
        delete normalized.vault_actor_context;
        // 表单仅提交动态连接参数；用户名和秘密在下发时由后端查询。
        Object.keys(normalized).forEach((key) => {
          if (isVaultAuthField(key, item)) delete normalized[key];
        });
      }
      Object.keys(normalized).forEach((key) => {
        if (key.startsWith('_')) {
          delete normalized[key];
        }
      });
      if (normalized.password === PASSWORD_PLACEHOLDER) {
        delete normalized.password;
      }
      if (normalized.community === PASSWORD_PLACEHOLDER) {
        delete normalized.community;
      }
      if (normalized.authkey === PASSWORD_PLACEHOLDER) {
        delete normalized.authkey;
      }
      if (normalized.privkey === PASSWORD_PLACEHOLDER) {
        delete normalized.privkey;
      }
      return normalized;
    })
    .filter((item) => Object.keys(item).length > 0);
};
