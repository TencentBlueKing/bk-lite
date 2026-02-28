import useApiClient from '@/utils/request';
import type { Tool, ToolPayload, MCPToolDefinition } from '../types/tool';

export const useToolApi = () => {
  const { get, post, put, del } = useApiClient();

  const fetchTools = async (): Promise<Tool[]> => {
    return await get('/opspilot/model_provider_mgmt/skill_tools/');
  };

  const createTool = async (data: ToolPayload): Promise<Tool> => {
    return await post('/opspilot/model_provider_mgmt/skill_tools/', data);
  };

  const updateTool = async (id: string, data: Partial<ToolPayload>): Promise<Tool> => {
    return await put(`/opspilot/model_provider_mgmt/skill_tools/${id}/`, data);
  };

  const deleteTool = async (id: string) => {
    return await del(`/opspilot/model_provider_mgmt/skill_tools/${id}/`);
  };

  const fetchAvailableTools = async (url: string, enable_auth?: boolean, auth_token?: string): Promise<MCPToolDefinition[]> => {
    return await post('/opspilot/model_provider_mgmt/skill_tools/get_mcp_tools/', {
      server_url: url,
      enable_auth: enable_auth || false,
      auth_token: auth_token || ''
    });
  };

  return {
    fetchTools,
    createTool,
    updateTool,
    deleteTool,
    fetchAvailableTools
  };
};
