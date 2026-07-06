import useApiClient from '@/utils/request';

export interface LoginAuthBinding {
  id: number;
  name: string;
  integration_instance: number;
  integration_instance_name: string;
  provider_key?: string;
  icon: string;
  description: string;
  order: number;
  enabled: boolean;
  external_field: string;
  platform_field: 'username' | 'phone' | 'email';
  unmatched_user_action: 'deny' | 'create';
  default_group_name: string;
  created_by?: string;
  created_at?: string;
  updated_by?: string;
  updated_at?: string;
}

export interface AvailableInstance {
  id: number;
  name: string;
  provider_key: string;
  provider_name: string;
}

export interface LoginAuthBindingPayload {
  name: string;
  integration_instance: number;
  icon?: string;
  description?: string;
  order?: number;
  enabled?: boolean;
  external_field: string;
  platform_field: 'username' | 'phone' | 'email';
  unmatched_user_action: 'deny' | 'create';
  default_group_name?: string;
}

export const useLoginAuthApi = () => {
  const { get, post, patch, del } = useApiClient();

  async function getLoginAuthBindings(params: any) {
    return await get('/system_mgmt/login_auth_binding/', { params })
  }

  async function createLoginAuthBinding(
    data: LoginAuthBindingPayload
  ): Promise<LoginAuthBinding> {
    return await post('/system_mgmt/login_auth_binding/', data);
  }

  async function updateLoginAuthBinding(
    id: number,
    data: Partial<LoginAuthBindingPayload>
  ): Promise<LoginAuthBinding> {
    return await patch(`/system_mgmt/login_auth_binding/${id}/`, data);
  }

  async function deleteLoginAuthBinding(id: number): Promise<void> {
    return await del(`/system_mgmt/login_auth_binding/${id}/`);
  }

  async function getAvailableInstances(): Promise<AvailableInstance[]> {
    return await get('/system_mgmt/integration_instance/available_instances/', {
      params: { capability: 'login_auth' },
    });
  }

  return {
    getLoginAuthBindings,
    createLoginAuthBinding,
    updateLoginAuthBinding,
    deleteLoginAuthBinding,
    getAvailableInstances,
  };
};
