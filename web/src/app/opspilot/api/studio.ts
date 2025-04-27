import useApiClient from '@/utils/request';

export const useStudioApi = () => {
  const { get, post, del, patch } = useApiClient();

  /**
   * Fetches logs for a specific bot.
   * @param params - Query parameters for fetching logs.
   */
  const fetchLogs = async (params: any): Promise<any> => {
    return get('/opspilot/bot_mgmt/history/search_log/', { params });
  };

  /**
   * Fetches channels for a specific bot.
   * @param botId - The ID of the bot.
   */
  const fetchChannels = async (botId: string | null): Promise<any[]> => {
    return get('/opspilot/bot_mgmt/bot/get_bot_channels/', { params: { bot_id: botId } });
  };

  /**
   * Updates a channel's configuration.
   * @param config - The updated channel configuration.
   */
  const updateChannel = async (config: any): Promise<void> => {
    return post('/opspilot/bot_mgmt/bot/update_bot_channel/', config);
  };

  /**
   * Deletes a studio by its ID.
   * @param studioId - The ID of the studio to delete.
   */
  const deleteStudio = async (studioId: number): Promise<void> => {
    return del(`/opspilot/bot_mgmt/bot/${studioId}/`);
  };

  /**
   * Fetches initial data for the studio settings page.
   * @param botId - The ID of the bot.
   */
  const fetchInitialData = async (botId: string | null): Promise<any> => {
    return Promise.all([
      get('/opspilot/bot_mgmt/rasa_model/'),
      get('/opspilot/model_provider_mgmt/llm/'),
      get('/opspilot/bot_mgmt/bot/get_bot_channels/', { params: { bot_id: botId } }),
      get(`/opspilot/bot_mgmt/bot/${botId}`)
    ]);
  };

  /**
   * Saves the bot configuration.
   * @param botId - The ID of the bot.
   * @param payload - The configuration payload.
   */
  const saveBotConfig = async (botId: string | null, payload: any): Promise<void> => {
    return patch(`/opspilot/bot_mgmt/bot/${botId}/`, payload);
  };

  /**
   * Toggles the online status of a bot.
   * @param botId - The ID of the bot.
   */
  const toggleOnlineStatus = async (botId: string | null): Promise<void> => {
    return post('/opspilot/bot_mgmt/bot/stop_pilot/', { bot_ids: [Number(botId)] });
  };

  /**
   * Fetches total token consumption.
   * @param params - Query parameters.
   */
  const fetchTokenConsumption = async (params: any): Promise<any> => {
    return get('/opspilot/bot_mgmt/get_total_token_consumption/', { params });
  };

  /**
   * Fetches token consumption overview data.
   * @param params - Query parameters.
   */
  const fetchTokenOverview = async (params: any): Promise<any> => {
    return get('/opspilot/bot_mgmt/get_token_consumption_overview/', { params });
  };

  /**
   * Fetches conversations line data.
   * @param params - Query parameters.
   */
  const fetchConversations = async (params: any): Promise<any> => {
    return get('/opspilot/bot_mgmt/get_conversations_line_data/', { params });
  };

  /**
   * Fetches active users line data.
   * @param params - Query parameters.
   */
  const fetchActiveUsers = async (params: any): Promise<any> => {
    return get('/opspilot/bot_mgmt/get_active_users_line_data/', { params });
  };

  return {
    fetchLogs,
    fetchChannels,
    updateChannel,
    deleteStudio,
    fetchInitialData,
    saveBotConfig,
    toggleOnlineStatus,
    fetchTokenConsumption,
    fetchTokenOverview,
    fetchConversations,
    fetchActiveUsers,
  };
};
