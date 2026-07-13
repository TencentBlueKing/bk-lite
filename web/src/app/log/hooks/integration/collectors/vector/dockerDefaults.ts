import { cloneDeep } from 'lodash';
import { TableDataItem } from '@/app/log/types';

/**
 * 把 Vector docker 采集的"编辑模式"表单数据转换成后端要求的扁平 content。
 *
 * 关键约定：
 * - 保存结构与加载结构必须一致（都使用扁平字段）
 * - `container_name_contains` / `container_name_exclude` 保存时 join 成 CSV 字符串
 * - 后端 Jinja2 模板再 split 回去（`server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2`）
 *
 * 此函数从 `useVectorConfig` 的 hook 闭包中抽取出来，便于单元测试。
 */
export const getVectorDockerParams = (
  formData: TableDataItem,
  configForm: TableDataItem
) => {
  const originalChild = cloneDeep(configForm?.child || {});
  const formDataCopy = cloneDeep(formData);

  // 容器过滤开关
  const enableContainerFilter =
    formDataCopy.containerFilter?.enabled || false;

  // 多行合并开关
  const enableMultiline = formDataCopy.multiline?.enabled || false;

  // 容器过滤参数（数组 → CSV 字符串）
  const containsArr = formDataCopy.container_name_contains || [];
  const excludeArr = formDataCopy.container_name_exclude || [];

  // 扁平化的 content 对象（9 个参数）
  const content: Record<string, unknown> = {
    endpoint: formDataCopy.endpoint,
    enable_container_filter: enableContainerFilter,
    container_name_contains: Array.isArray(containsArr)
      ? containsArr.join(',')
      : containsArr,
    container_name_exclude: Array.isArray(excludeArr)
      ? excludeArr.join(',')
      : excludeArr,
    enable_multiline: enableMultiline,
    multiline_mode: formDataCopy.multiline?.mode || 'continue_through',
    multiline_pattern:
      formDataCopy.multiline?.condition_pattern || '^[\\s]+',
    multiline_start_pattern:
      formDataCopy.multiline?.start_pattern || '^[^\\s]',
    multiline_timeout_ms: formDataCopy.multiline?.timeout_ms || 1000
  };

  return {
    child: {
      ...originalChild,
      content
    }
  };
};

/**
 * 把后端拉回的 child.content 反解为编辑表单默认值。
 *
 * 必须与 `getVectorDockerParams` 写入结构完全一致，否则会出现
 * "编辑时多行合并开关、容器过滤开关显示为关闭"等 bug。
 */
export const getVectorDockerDefaultForm = (formData: TableDataItem) => {
  const content = formData?.child?.content || {};

  // CSV 字符串 → 数组（与 getParams 中的 join(',') 互逆）
  const splitCsv = (s: unknown): string[] => {
    if (typeof s !== 'string' || !s) return [];
    return s
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean);
  };

  return {
    endpoint: content.endpoint || 'unix:///var/run/docker.sock',
    containerFilter: {
      enabled: !!content.enable_container_filter
    },
    container_name_contains: splitCsv(content.container_name_contains),
    container_name_exclude: splitCsv(content.container_name_exclude),
    multiline: {
      enabled: !!content.enable_multiline,
      mode: content.multiline_mode || 'continue_through',
      condition_pattern: content.multiline_pattern || '^[\\s]+',
      start_pattern: content.multiline_start_pattern || '^[^\\s]',
      timeout_ms: content.multiline_timeout_ms || 1000
    }
  };
};