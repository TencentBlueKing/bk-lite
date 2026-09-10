import useApiClient from '@/utils/request';
import type {
  CredentialCreatePayload,
  CredentialGroupOption,
  CredentialItem,
  CredentialTypeItem,
} from '@/components/credential-picker/types';

interface Page<T> {
  count: number;
  items: T[];
}

function asPage<T>(data: T[] | Page<T> | undefined): Page<T> {
  if (Array.isArray(data)) {
    return { count: data.length, items: data };
  }
  return { count: data?.count || 0, items: data?.items || [] };
}

function asList<T>(data: T[] | Page<T> | undefined): T[] {
  return asPage(data).items;
}

export const useCredentialApi = () => {
  const { get, post, patch, del } = useApiClient();

  async function getCredentialTypes(params?: {
    search?: string;
    category?: string;
    page?: number;
    page_size?: number;
  }): Promise<Page<CredentialTypeItem>> {
    const data = await get<Page<CredentialTypeItem> | CredentialTypeItem[]>(
      '/system_mgmt/credential_type/',
      { params },
    );
    return asPage(data);
  }

  async function getCredentialType(key: string): Promise<CredentialTypeItem> {
    return await get(`/system_mgmt/credential_type/${key}/`);
  }

  async function createCredentialType(payload: {
    key: string;
    name: string;
    categories: string[];
    fields?: CredentialTypeItem['fields'];
  }): Promise<CredentialTypeItem> {
    return await post('/system_mgmt/credential_type/', payload);
  }

  async function updateCredentialType(
    key: string,
    payload: Partial<Pick<CredentialTypeItem, 'name' | 'categories' | 'fields'>>,
  ): Promise<CredentialTypeItem> {
    return await patch(`/system_mgmt/credential_type/${key}/`, payload);
  }

  async function deleteCredentialType(key: string): Promise<void> {
    await del(`/system_mgmt/credential_type/${key}/`);
  }

  async function getCredentials(params?: {
    search?: string;
    category?: string;
    type?: string;
    group_id?: number;
    page?: number;
    page_size?: number;
  }): Promise<Page<CredentialItem>> {
    const data = await get<Page<CredentialItem> | CredentialItem[]>('/system_mgmt/credential/', {
      params,
    });
    return asPage(data);
  }

  async function getCredential(credentialId: string): Promise<CredentialItem> {
    return await get(`/system_mgmt/credential/${credentialId}/`);
  }

  async function createCredential(payload: CredentialCreatePayload): Promise<CredentialItem> {
    return await post('/system_mgmt/credential/', payload);
  }

  async function updateCredential(
    credentialId: string,
    payload: Partial<CredentialCreatePayload> & { disabled?: boolean; fields?: Record<string, unknown> },
  ): Promise<CredentialItem> {
    return await patch(`/system_mgmt/credential/${credentialId}/`, payload);
  }

  async function deleteCredential(credentialId: string): Promise<void> {
    await del(`/system_mgmt/credential/${credentialId}/`, {
      suppressErrorNotification: true,
    });
  }

  async function setCredentialDisabled(credentialId: string, disabled: boolean): Promise<CredentialItem> {
    return await post(`/system_mgmt/credential/${credentialId}/disable/`, { disabled });
  }

  async function getAssignableGroups(): Promise<CredentialGroupOption[]> {
    return asList(await get('/system_mgmt/credential/assignable_groups/'));
  }

  async function getUsableGroups(): Promise<CredentialGroupOption[]> {
    return asList(await get('/system_mgmt/credential/usable_groups/'));
  }

  return {
    getCredentialTypes,
    getCredentialType,
    createCredentialType,
    updateCredentialType,
    deleteCredentialType,
    getCredentials,
    getCredential,
    createCredential,
    updateCredential,
    deleteCredential,
    setCredentialDisabled,
    getAssignableGroups,
    getUsableGroups,
  };
};
