import useApiClient from '@/utils/request';
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
    listSelectableCredentials,
    listSelectableTypes,
    createCredential,
  };
};
