export const SCRIPT_ATTACH_INSTANCE_FIELD = 'attach_instance_id';

interface ScriptAttachObject {
  instance_id_keys?: string[] | null;
  level?: string | null;
  name?: string | null;
};

/** 与后端单键判断一致：只有 instance_id，且不含 resource_id。 */
export const isSingleKeyInstanceObject = (object?: ScriptAttachObject | null) => {
  const raw = (object?.instance_id_keys || [])
    .map((key) => String(key || '').trim())
    .filter(Boolean);
  const keys = raw.length
    ? raw
    : String(object?.level || '').trim() === 'derivative' && String(object?.name || '').trim()
      ? ['instance_id', String(object?.name || '').trim()]
      : ['instance_id'];
  return keys.length === 1 && keys[0] === 'instance_id' && !keys.includes('resource_id');
};

export const scriptAttachInstanceLabel = (item: {
  instance_name?: string;
  ip?: string;
  instance_id?: string;
}) => {
  const name = String(item.instance_name || item.instance_id || '').trim();
  const ip = String(item.ip || '').trim();
  if (name && ip && !name.includes(ip)) {
    return `${name}（${ip}）`;
  }
  return name || ip;
};

export const rewriteScriptAttachConfig = <T extends Record<string, any>>(config: T): T => {
  if (!config) return config;
  const columns = Array.isArray(config.table_columns) ? config.table_columns : [];
  const kept = columns.filter(
    (column) =>
      column?.name !== 'instance_name' &&
      column?.name !== 'group_ids' &&
      column?.name !== SCRIPT_ATTACH_INSTANCE_FIELD
  );
  const attachColumn = {
    name: SCRIPT_ATTACH_INSTANCE_FIELD,
    label: '选择实例',
    label_en: 'Instance',
    type: 'select',
    required: true,
    options_key: 'attach_instance_option',
    description: '脚本会添加到所选实例上，不会另外新建实例。',
    description_en: 'The script is added to the selected instance. A new instance is not created.',
    tooltip: '脚本挂在已有实例上，作为该实例的一种采集。',
    tooltip_en: 'The script is one of the collections on an existing instance.',
    widget_props: {
      placeholder: '请选择实例',
      placeholder_en: 'Select an instance'
    },
    change_handler: {
      type: 'script_attach',
      target_field: 'instance_id'
    }
  };
  const nodeIndex = kept.findIndex((column) => column?.name === 'node_ids');
  const nextColumns = [...kept];
  if (nodeIndex >= 0) {
    nextColumns.splice(nodeIndex + 1, 0, attachColumn);
  } else {
    nextColumns.unshift(attachColumn);
  }
  return {
    ...config,
    instance_id: '',
    table_columns: nextColumns
  };
};
