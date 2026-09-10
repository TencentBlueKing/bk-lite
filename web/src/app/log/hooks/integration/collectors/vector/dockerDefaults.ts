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
 * `get_config_content` 会先解析已经渲染的 TOML，因此正常响应中的采集参数
 * 位于 `content.sources.docker_<config_id>`（docker_host / include_containers /
 * exclude_containers / multiline）。同时兼容尚未经过模板渲染的扁平 enable_* 结构。
 *
 * 无过滤字段时容器过滤关闭；无 multiline 时多行关闭。缺字段不得当成
 * 模板默认排除列表（vector,logspout）。
 */
export const getVectorDockerDefaultForm = (formData: TableDataItem) => {
  const content = formData?.child?.content || {};
  const sources = content.sources || {};
  const sourceKey =
    Object.keys(sources).find((key) => key.startsWith('docker_')) || '';
  const sourceData = sources[sourceKey] || content;

  // CSV 字符串或 TOML 数组 → 表单数组（与 getParams 中的 join(',') 互逆）
  const splitCsv = (s: unknown): string[] => {
    if (Array.isArray(s)) {
      return s.map((v) => String(v).trim()).filter(Boolean);
    }
    if (typeof s !== 'string' || !s) return [];
    return s
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean);
  };

  const hasInclude = Array.isArray(sourceData.include_containers);
  const hasExclude = Array.isArray(sourceData.exclude_containers);
  const enableContainerFilter =
    hasInclude || hasExclude || !!sourceData.enable_container_filter;

  const multilineNode = sourceData.multiline;
  const enableMultiline =
    !!multilineNode?.mode || !!sourceData.enable_multiline;

  return {
    endpoint:
      sourceData.docker_host ||
      sourceData.endpoint ||
      'unix:///var/run/docker.sock',
    containerFilter: {
      enabled: enableContainerFilter
    },
    container_name_contains: hasInclude
      ? splitCsv(sourceData.include_containers)
      : splitCsv(sourceData.container_name_contains),
    container_name_exclude: hasExclude
      ? splitCsv(sourceData.exclude_containers)
      : splitCsv(sourceData.container_name_exclude),
    multiline: {
      enabled: enableMultiline,
      mode:
        multilineNode?.mode || sourceData.multiline_mode || 'continue_through',
      condition_pattern:
        multilineNode?.condition_pattern ||
        sourceData.multiline_pattern ||
        '^[\\s]+',
      start_pattern:
        multilineNode?.start_pattern ||
        sourceData.multiline_start_pattern ||
        '^[^\\s]',
      timeout_ms:
        multilineNode?.timeout_ms || sourceData.multiline_timeout_ms || 1000
    }
  };
};
