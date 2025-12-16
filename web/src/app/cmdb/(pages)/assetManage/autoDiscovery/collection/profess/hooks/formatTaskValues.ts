import { ENTER_TYPE, PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import { TreeNode, ModelItem } from '@/app/cmdb/types/autoDiscovery';
import { BaseTaskRef } from '../components/baseTask';

interface FormatTaskValuesOptions {
  values: any;
  baseRef: React.RefObject<BaseTaskRef>;
  selectedNode: TreeNode;
  modelItem: ModelItem;
  modelId: string;
  formatCycleValue: (values: any) => any;
}

interface CredentialConfig {
  [key: string]: string | ((value: any) => any);
}

/**
 * 格式化任务表单的公共字段
 * 只处理所有任务类型都有的字段，实例相关逻辑由各任务自行处理
 */
export const formatTaskValues = ({
  values,
  baseRef,
  selectedNode,
  modelItem,
  modelId,
  formatCycleValue,
}: FormatTaskValuesOptions) => {
  const driverType = selectedNode.tabItems?.find(
    (item) => item.model_id === modelId
  )?.type;

  const accessPoint = baseRef.current?.accessPoints.find(
    (item: any) => item.value === values.accessPointId
  );

  return {
    name: values.taskName,
    input_method: values.enterType === ENTER_TYPE.APPROVAL ? 1 : 0,
    timeout: values.timeout || 600,
    scan_cycle: formatCycleValue(values),
    access_point: accessPoint?.origin && [accessPoint.origin],
    model_id: modelId,
    task_type: modelItem.task_type,
    driver_type: driverType,
    accessPointId: values.access_point?.[0]?.id,
    team: values.organization || [],
    params: {},
  };
};

/**
 * 构建凭据对象，自动处理密码占位符
 * @param credentialMap 凭据字段映射，key为目标字段名，value为源字段名或处理函数
 * @param values 表单值
 * @returns 处理后的凭据对象
 */
export const buildCredential = (
  credentialMap: CredentialConfig,
  values: any
): Record<string, any> => {
  const credential: Record<string, any> = {};

  Object.entries(credentialMap).forEach(([targetKey, sourceConfig]) => {
    if (typeof sourceConfig === 'function') {
      const result = sourceConfig(values);
      if (result !== undefined) {
        credential[targetKey] = result;
      }
    } else {
      const value = values[sourceConfig];

      if (value && value !== PASSWORD_PLACEHOLDER) {
        credential[targetKey] = value;
      } else if (value !== PASSWORD_PLACEHOLDER && value !== undefined) {
        credential[targetKey] = value;
      }
    }
  });

  return credential;
};
