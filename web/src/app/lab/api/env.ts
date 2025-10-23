import useApiClient from "@/utils/request";

const useLabEnv = () => {
  const { get, put, post, del } = useApiClient();

  // ========== Lab 环境管理接口 ==========

  // 获取环境列表
  const getEnvList = async (params?: any) => {
    return await get(`/lab/environments/`, params);
  };

  // 新增环境
  const addEnv = async (data: any) => {
    return await post(`/lab/environments/`, data);
  };

  // 获取环境详情
  const getEnvDetail = async (id: number | string) => {
    return await get(`/lab/environments/${id}/`);
  };

  // 更新环境
  const updateEnv = async (id: number | string, data: any) => {
    return await put(`/lab/environments/${id}/`, data);
  };

  // 删除环境
  const deleteEnv = async (id: number | string) => {
    return await del(`/lab/environments/${id}/`);
  };

  // 启动环境
  const startEnv = async (id: number | string) => {
    return await post(`/lab/environments/${id}/start/`);
  };

  // 停止环境
  const stopEnv = async (id: number | string) => {
    return await post(`/lab/environments/${id}/stop/`);
  };

  // 重启环境
  const restartEnv = async (id: number | string) => {
    return await post(`/lab/environments/${id}/restart/`);
  };

  // 获取环境状态
  const getEnvStatus = async (id: number | string) => {
    return await get(`/lab/environments/${id}/status/`);
  };

  // 获取正在运行的环境列表
  const getRunningEnvs = async () => {
    return await get(`/lab/environments/running/`);
  };

  // 获取环境统计摘要
  const getEnvSummary = async () => {
    return await get(`/lab/environments/summary/`);
  };

  // ========== 基础设施实例管理接口 ==========

  // 获取实例列表
  const getInstanceList = async (params?: any) => {
    return await get(`/lab/infra-instances/`, params);
  };

  // 新增实例
  const addInstance = async (data: any) => {
    return await post(`/lab/infra-instances/`, data);
  };

  // 获取实例详情
  const getInstanceDetail = async (id: number | string) => {
    return await get(`/lab/infra-instances/${id}/`);
  };

  // 更新实例
  const updateInstance = async (id: number | string, data: any) => {
    return await put(`/lab/infra-instances/${id}/`, data);
  };

  // 删除实例
  const deleteInstance = async (id: number | string) => {
    return await del(`/lab/infra-instances/${id}/`);
  };

  // // 启动实例
  // const startInstance = async (id: number | string) => {
  //   return await post(`/lab/infra-instances/${id}/start/`);
  // };

  // // 停止实例
  // const stopInstance = async (id: number | string) => {
  //   return await post(`/lab/infra-instances/${id}/stop/`);
  // };

  // // 获取实例日志
  // const getInstanceLogs = async (id: number | string, lines?: number) => {
  //   const url = lines ? `/lab/infra-instances/${id}/logs/?lines=${lines}` : `/lab/infra-instances/${id}/logs/`;
  //   return await get(url);
  // };

  // // 同步实例状态
  // const syncInstanceStatus = async (id: number | string) => {
  //   return await post(`/lab/infra-instances/${id}/sync_status/`);
  // };

  // // 获取正在运行的实例列表
  // const getRunningInstances = async () => {
  //   return await get(`/lab/infra-instances/running/`);
  // };

  return {
    // Lab 环境接口
    getEnvList,
    addEnv,
    getEnvDetail,
    updateEnv,
    deleteEnv,
    startEnv,
    stopEnv,
    restartEnv,
    getEnvStatus,
    getRunningEnvs,
    getEnvSummary,
    
    // 基础设施实例接口
    getInstanceList,
    addInstance,
    getInstanceDetail,
    updateInstance,
    deleteInstance,
    // startInstance,
    // stopInstance,
    // getInstanceLogs,
    // syncInstanceStatus,
    // getRunningInstances,
  };
};

export default useLabEnv;
