import useApiClient from '@/utils/request';
export const useChannelApi = () => {
  const { get, post, put, del } = useApiClient();

  async function getChannelData(params: any) {
    return await get('/system_mgmt/channel/', { params });
  }

  async function getChannelDetail(id: string) {
    return await get(`/system_mgmt/channel/${id}`);
  }

  async function addChannel(params: any) {
    return await post('/system_mgmt/channel/', params);
  }

  async function updateChannel(params: any) {
    return await put(`/system_mgmt/channel/${params.id}/`, params);
  }

  async function deleteChannel(params: any) {
    return await del(`/system_mgmt/channel/${params.id}/`);
  }

  async function getChannelTemp(params: any) {
    return await get("/system_mgmt/channel_template/", { params });
  }

  return {
    getChannelData,
    getChannelDetail,
    addChannel,
    updateChannel,
    deleteChannel,
    getChannelTemp,
  }
}
