import useApiClient from '@/utils/request';
import type { MenuItem } from '@/types';
import type {
  CredentialCreatePayload,
  CredentialItem,
  CredentialTypeItem,
} from './types';

function asList<T>(data: T[] | { items?: T[] } | undefined): T[] {
  if (Array.isArray(data)) {
    return data;
  }
  return data?.items || [];
}

export const useCredentialPickerApi = () => {
  const { get, post } = useApiClient();

  async function getCredentialPermissions(): Promise<string[]> {
    // 选择器可在 CMDB 等应用中使用，当前应用的菜单上下文不包含系统管理授权。
    try {
      const menus = await get<MenuItem[]>('/core/api/get_user_menus/', {
        params: { name: 'system-manager' },
      });
      const operations = (items: MenuItem[]): string[] => items.flatMap((item) => [
        ...(item.name === 'credential' ? item.operation || [] : []),
        ...operations(item.children || []),
      ]);
      return operations(menus || []);
    } catch {
      // 权限不可确认时保持禁用，不影响已有凭据的选择。
      return [];
    }
  }

  async function listSelectableCredentials(params: {
    category?: string;
    type?: string;
    search?: string;
  }): Promise<CredentialItem[]> {
    const data = await get<CredentialItem[] | { items: CredentialItem[] }>(
      '/system_mgmt/credential/selectable/',
      { params },
    );
    return asList(data);
  }

  async function listSelectableTypes(params?: { category?: string }): Promise<CredentialTypeItem[]> {
    const data = await get<CredentialTypeItem[] | { items: CredentialTypeItem[] }>(
      '/system_mgmt/credential_type/selectable/',
      { params },
    );
    return asList(data);
  }

  async function createCredential(payload: CredentialCreatePayload): Promise<CredentialItem> {
    return await post('/system_mgmt/credential/', payload);
  }

  return {
    getCredentialPermissions,
    listSelectableCredentials,
    listSelectableTypes,
    createCredential,
  };
};
