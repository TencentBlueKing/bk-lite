import useApiClient from '@/utils/request';

export interface MemorySpace {
  id: number;
  name: string;
  introduction: string;
  scope: 'personal' | 'team';
  team: number[];
  write_rule: string;
  default_model: string;
  memory_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Memory {
  id: number;
  memory_space: number;
  title: string;
  content: string;
  owner_username: string;
  owner_domain: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export const useMemoryApi = () => {
  const { get, post, put, del } = useApiClient();

  const fetchMemorySpaces = async (): Promise<MemorySpace[]> => {
    return await get('/opspilot/memory_mgmt/memory_space/');
  };

  const fetchMemorySpace = async (id: number): Promise<MemorySpace> => {
    const res = await get(`/opspilot/memory_mgmt/memory_space/${id}/`);
    return res.data || res;
  };

  const createMemorySpace = async (data: Partial<MemorySpace>): Promise<MemorySpace> => {
    return await post('/opspilot/memory_mgmt/memory_space/', data);
  };

  const updateMemorySpace = async (id: number, data: Partial<MemorySpace>): Promise<MemorySpace> => {
    return await put(`/opspilot/memory_mgmt/memory_space/${id}/`, data);
  };

  const deleteMemorySpace = async (id: number) => {
    return await del(`/opspilot/memory_mgmt/memory_space/${id}/`);
  };

  const fetchMemories = async (memorySpaceId?: number): Promise<Memory[]> => {
    const params = memorySpaceId ? `?memory_space=${memorySpaceId}` : '';
    return await get(`/opspilot/memory_mgmt/memory/${params}`);
  };

  const createMemory = async (data: Partial<Memory>): Promise<Memory> => {
    return await post('/opspilot/memory_mgmt/memory/', data);
  };

  const updateMemory = async (id: number, data: Partial<Memory>): Promise<Memory> => {
    return await put(`/opspilot/memory_mgmt/memory/${id}/`, data);
  };

  const deleteMemory = async (id: number) => {
    return await del(`/opspilot/memory_mgmt/memory/${id}/`);
  };

  const testMemoryWrite = async (data: { 
    input: string; 
    write_rule: string; 
    model_id: number;
    reference_memory_id?: number 
  }): Promise<{ result: string }> => {
    return await post('/opspilot/memory_mgmt/memory_space/test_write/', data);
  };

  return {
    fetchMemorySpaces,
    fetchMemorySpace,
    createMemorySpace,
    updateMemorySpace,
    deleteMemorySpace,
    fetchMemories,
    createMemory,
    updateMemory,
    deleteMemory,
    testMemoryWrite,
  };
};
