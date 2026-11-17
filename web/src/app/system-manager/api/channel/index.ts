import useApiClient from '@/utils/request';
export const useChannelApi = () => {
  const { get, post, put, del } = useApiClient();

  async function getChannelData(params: any) {
    return await get('/system_mgmt/channel/', { params });
  }

  async function getNotificationTagCatalog() {
    const pageSize = 500;
    const rows: Array<{ key: string; value: string }> = [];
    let page = 1;
    let count = 0;
    do {
      const data = await get('/system_mgmt/channel/tag_catalog/', {
        params: { page, page_size: pageSize },
      });
      const results = Array.isArray(data?.results) ? data.results : [];
      count = Number(data?.count || 0);
      rows.push(...results);
      if (results.length === 0 || rows.length >= count) {
        break;
      }
      page += 1;
    } while (page <= 1000);
    return rows;
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

  async function testChannel(params: any) {
    return await post('/system_mgmt/channel/test_send/', params);
  }

  async function getGroupAccountAssociationOptions(channelType: string) {
    return await get('/system_mgmt/channel/account_association_options/', {
      params: { channel_type: channelType },
    });
  }

  return {
    getChannelData,
    getNotificationTagCatalog,
    getChannelDetail,
    addChannel,
    updateChannel,
    deleteChannel,
    getChannelTemp,
    testChannel,
    getGroupAccountAssociationOptions,
  }
}
