import { cloneDeep } from 'lodash';
import { TableDataItem } from '@/app/log/types';
import { normalizePasswordWhitespace } from '@/components/password/normalizePasswordWhitespace';

const splitCsv = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  if (typeof value !== 'string' || !value) {
    return [];
  }
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
};

const getSourceData = (content: TableDataItem) => {
  const sources = content?.sources || {};
  const sourceKey =
    Object.keys(sources).find((key) => key.startsWith('kafka_subscribe_')) ||
    '';
  return sources[sourceKey] || content;
};

export const buildKafkaSubscribeContent = (formData: TableDataItem) => {
  const formDataCopy = cloneDeep(formData);
  const saslEnabled = !!formDataCopy.sasl?.enabled;
  const content: Record<string, unknown> = {
    topics: formDataCopy.topics || [],
    bootstrap_servers: formDataCopy.bootstrap_servers || [],
    group_id: formDataCopy.group_id || '',
    auto_offset_reset: formDataCopy.auto_offset_reset || 'latest',
    sasl_enabled: saslEnabled,
    tls_enabled: !!formDataCopy.tls_enabled
  };

  if (saslEnabled) {
    content.sasl_mechanism = formDataCopy.sasl?.mechanism || 'PLAIN';
    content.sasl_username = normalizePasswordWhitespace(
      String(formDataCopy.sasl?.username || '')
    ).value;
    content.sasl_password = normalizePasswordWhitespace(
      String(formDataCopy.sasl?.password || '')
    ).value;
  }

  return content;
};

export const getVectorKafkaSubscribeParams = (
  formData: TableDataItem,
  configForm: TableDataItem
) => {
  const originalChild = cloneDeep(configForm?.child || {});
  return {
    child: {
      ...originalChild,
      content: buildKafkaSubscribeContent(formData)
    }
  };
};

export const getVectorKafkaSubscribeDefaultForm = (formData: TableDataItem) => {
  const content = formData?.child?.content || {};
  const sourceData = getSourceData(content);
  const sasl = sourceData.sasl || {};
  const saslEnabled = !!(sourceData.sasl_enabled ?? sasl.enabled);

  return {
    topics: sourceData.topics || [],
    bootstrap_servers: splitCsv(sourceData.bootstrap_servers),
    group_id: sourceData.group_id || '',
    auto_offset_reset: sourceData.auto_offset_reset || 'latest',
    sasl: {
      enabled: saslEnabled,
      mechanism: sourceData.sasl_mechanism || sasl.mechanism || 'PLAIN',
      username: sourceData.sasl_username || sasl.username || '',
      password: sourceData.sasl_password || sasl.password || ''
    },
    tls_enabled: !!(sourceData.tls_enabled ?? sourceData.tls?.enabled)
  };
};
