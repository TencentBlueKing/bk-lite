import { cloneDeep } from 'lodash';
import { TableDataItem } from '@/app/log/types';

/**
 * 把 Vector 文件采集的"编辑模式"表单数据转换成后端要求的扁平 content。
 *
 * 关键约定：保存结构 = 加载结构，两者都使用扁平字段（如 `content.multiline`），
 * 与后端 Jinja2 模板（`server/apps/log/support-files/plugins/Vector/file/*`）保持一致。
 *
 * 此函数从 `useVectorConfig` 的 hook 闭包中抽取出来，便于单元测试。
 */
export const getVectorFileParams = (
  formData: TableDataItem,
  configForm: TableDataItem
) => {
  const originalChild = cloneDeep(configForm?.child || {});
  const formDataCopy = cloneDeep(formData);

  // 构建扁平 content 对象
  const content: Record<string, unknown> = {
    include: formDataCopy.include || [],
    exclude: formDataCopy.exclude || [],
    read_from: formDataCopy.read_from,
    ignore_older_secs: formDataCopy.ignore_older_secs,
    encoding_charset: formDataCopy.encoding_charset
  };

  // 处理 parser_type
  if (formDataCopy.parser_type) {
    content.parser_type = formDataCopy.parser_type;
  }

  // 处理 multiline（仅在开启时写入，禁用时不写入子字段，避免干扰后端模板渲染）
  if (formDataCopy.multiline?.enabled) {
    content.multiline = {
      condition_pattern: formDataCopy.multiline.condition_pattern,
      mode: formDataCopy.multiline.mode,
      start_pattern: formDataCopy.multiline.start_pattern,
      timeout_ms: formDataCopy.multiline.timeout_ms
    };
  }

  return {
    child: {
      ...originalChild,
      content
    }
  };
};

/**
 * 从后端拉回的 child.content 中反解出编辑表单的默认值。
 *
 * 必须与 `getVectorFileParams` 写入结构完全一致，否则会出现
 * "保存后再次打开，开关/字段全部丢失"的 bug。
 */
export const getVectorFileDefaultForm = (formData: TableDataItem) => {
  const content = formData?.child?.content || {};

  return {
    include: content.include || [],
    exclude: content.exclude || [],
    read_from: content.read_from || 'beginning',
    ignore_older_secs: content.ignore_older_secs || 86400,
    encoding_charset: content.encoding_charset || 'utf-8',
    parser_type: content.parser_type || '',
    multiline: {
      enabled: !!content.multiline?.mode,
      mode: content.multiline?.mode || 'continue_through',
      start_pattern: content.multiline?.start_pattern || '',
      timeout_ms: content.multiline?.timeout_ms || 1000,
      condition_pattern: content.multiline?.condition_pattern || ''
    }
  };
};