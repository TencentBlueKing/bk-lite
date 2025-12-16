/**
 * Node Manager 统一API Hook
 * 聚合所有API方法，提供便捷的单一导入方式
 */
import useCloudRegionApi from './useCloudRegionApi';
import useNodeApi from './useNodeApi';
import useConfigApi from './useConfigApi';
import useVariableApi from './useVariableApi';
import useCollectorApi from './useCollectorApi';
import useControllerApi from './useControllerApi';
import usePackageApi from './usePackageApi';

const useNodeManagerApi = () => {
  const cloudRegionApi = useCloudRegionApi(); // 云区域管理
  const nodeApi = useNodeApi(); // 节点管理
  const configApi = useConfigApi(); // 配置管理
  const variableApi = useVariableApi(); // 环境变量管理
  const collectorApi = useCollectorApi(); // 采集器管理
  const controllerApi = useControllerApi(); // 控制器管理
  const packageApi = usePackageApi(); // 包管理

  return {
    ...cloudRegionApi,
    ...nodeApi,
    ...configApi,
    ...variableApi,
    ...collectorApi,
    ...controllerApi,
    ...packageApi,
  };
};

export default useNodeManagerApi;

export type { PackageParams } from './usePackageApi';
