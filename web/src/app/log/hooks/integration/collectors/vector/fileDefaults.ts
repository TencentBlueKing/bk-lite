import { cloneDeep } from 'lodash';
import { TableDataItem } from '@/app/log/types';

/**
 * 把 Vector 文件采集的"编辑模式"表单数据转换成后端模板需要的扁平 content。
 *
 * 保存时提交模板变量（如 `content.multiline`）；再次加载时，后端返回模板渲染并
 * 解析后的 TOML 结构，由 `getVectorFileDefaultForm` 负责反解。
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
 * `get_config_content` 会先解析已经渲染的 TOML，因此正常响应中的采集参数
 * 位于 `content.sources.file_<config_id>`；同时兼容尚未经过模板渲染的扁平结构。
 */
export const getVectorFileDefaultForm = (formData: TableDataItem) => {
  const content = formData?.child?.content || {};
  const sources = content.sources || {};
  const sourceKey =
    Object.keys(sources).find((key) => key.startsWith('file_')) || '';
  const sourceData = sources[sourceKey] || content;

  return {
    include: sourceData.include || [],
    exclude: sourceData.exclude || [],
    read_from: sourceData.read_from || 'beginning',
    ignore_older_secs: sourceData.ignore_older_secs || 86400,
    encoding_charset:
      sourceData.encoding?.charset ||
      sourceData.encoding_charset ||
      'utf-8',
    parser_type: sourceData.parser_type || '',
    multiline: {
      enabled: !!sourceData.multiline?.mode,
      mode: sourceData.multiline?.mode || 'continue_through',
      start_pattern: sourceData.multiline?.start_pattern || '',
      timeout_ms: sourceData.multiline?.timeout_ms || 1000,
      condition_pattern: sourceData.multiline?.condition_pattern || ''
    }
  };
};
