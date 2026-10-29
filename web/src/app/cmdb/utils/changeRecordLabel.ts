type Translate = (id: string, defaultMessage?: string) => string;

const MODEL_OBJECT_IDS: Record<string, string> = {
  资产实例: 'OperationLog.objectOpts.instance',
  模型管理: 'OperationLog.objectOpts.model',
  采集任务: 'OperationLog.objectOpts.collectTask',
};

export function localizedEnumLabel(
  t: Translate,
  catalogPrefix: string,
  key: string | undefined,
  remote: Record<string, string> = {},
): string {
  if (!key) return '';
  const id = `${catalogPrefix}.${key}`;
  const local = t(id);
  if (local && local !== id) return local;
  return remote[key] || key;
}

export function localizedModelObject(t: Translate, value: string | undefined): string {
  if (!value) return '';
  const id = MODEL_OBJECT_IDS[value];
  if (!id) return value;
  const local = t(id);
  return local && local !== id ? local : value;
}
