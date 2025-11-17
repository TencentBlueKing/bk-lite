import useApiClient from '@/utils/request';

export const useToolApi = () => {
  const { get, post, put, del } = useApiClient();

  const fetchTools = async () => {
    return await get('/opspilot/model_provider_mgmt/skill_tools/');
  };

  const createTool = async (data: any) => {
    return await post('/opspilot/model_provider_mgmt/skill_tools/', data);
  };

  const updateTool = async (id: string, data: any) => {
    return await put(`/opspilot/model_provider_mgmt/skill_tools/${id}/`, data);
  };

  const deleteTool = async (id: string) => {
    return await del(`/opspilot/model_provider_mgmt/skill_tools/${id}/`);
  };

  const fetchAvailableTools = async (url: string) => {
    return await post('/opspilot/model_provider_mgmt/skill_tools/get_mcp_tools/', { server_url: url });
  };

  return { 
    fetchTools, 
    createTool, 
    updateTool, 
    deleteTool, 
    fetchAvailableTools 
  };
};
