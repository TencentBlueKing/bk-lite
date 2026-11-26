export interface CatalogField {
  type: string;
  label: string;
  group: 'basic' | 'senior' | 'scene';
  key?: string;
  placeholder?: string;
}

export const BASIC_FIELDS: CatalogField[] = [
  { type: 'input', label: '单行文本', group: 'basic' },
  { type: 'textarea', label: '多行文本', group: 'basic' },
  { type: 'number', label: '数值', group: 'basic' },
  { type: 'radio', label: '单选框', group: 'basic' },
  { type: 'checkbox', label: '复选框', group: 'basic' },
  { type: 'select', label: '单选下拉', group: 'basic' },
  { type: 'multiselect', label: '多选下拉', group: 'basic' },
  { type: 'cascade', label: '单选级联', group: 'basic' },
  { type: 'multiCascade', label: '多选级联', group: 'basic' },
  { type: 'date', label: '日期', group: 'basic' },
  { type: 'datetime', label: '日期时间', group: 'basic' },
  { type: 'time', label: '时间', group: 'basic' },
  { type: 'dateRange', label: '日期范围', group: 'basic' },
  { type: 'richtext', label: '富文本', group: 'basic' },
  { type: 'user', label: '单选人员', group: 'basic' },
  { type: 'multiUser', label: '多选人员', group: 'basic' },
];

export const SENIOR_FIELDS: CatalogField[] = [
  { type: 'section', label: '分组', group: 'senior' },
  { type: 'table', label: '子表单', group: 'senior' },
  { type: 'task', label: '任务', group: 'senior' },
  { type: 'tab', label: '标签页', group: 'senior' },
  { type: 'attachment', label: '附件', group: 'senior' },
  { type: 'userGroup', label: '单选用户组', group: 'senior' },
  { type: 'multiUserGroup', label: '多选用户组', group: 'senior' },
  { type: 'cmdb', label: '单选CMDB业务', group: 'senior' },
  { type: 'multiCmdb', label: '多选CMDB业务', group: 'senior' },
  { type: 'calculate', label: '计算字段', group: 'senior' },
  { type: 'link', label: '链接', group: 'senior' },
  { type: 'subProcessForm', label: '子流程表单', group: 'senior' },
  { type: 'nestedTable', label: '嵌套表格', group: 'senior' },
  { type: 'organization', label: '单选组织', group: 'senior' },
  { type: 'signature', label: '电子签名', group: 'senior' },
  { type: 'singleAssociateConfig', label: '单选配置项', group: 'senior' },
  { type: 'associateConfig', label: '多选配置项', group: 'senior' },
  { type: 'cab', label: 'CAB投票', group: 'senior' },
];

export const SCENE_FIELDS: CatalogField[] = [
  { type: 'textarea', label: '问题描述', group: 'scene', key: 'problem_desc', placeholder: '请输入' },
  { type: 'cascade', label: '问题分类', group: 'scene', key: 'problem_category', placeholder: '请选择' },
  { type: 'organization', label: '问题处理组', group: 'scene', key: 'problem_group', placeholder: '请选择' },
  { type: 'textarea', label: '问题根本原因', group: 'scene', key: 'root_cause' },
  { type: 'select', label: '解决代码', group: 'scene', key: 'resolution_code', placeholder: '请选择' },
  { type: 'textarea', label: '临时解决方案', group: 'scene', key: 'temp_solution' },
  { type: 'textarea', label: '根本解决方案', group: 'scene', key: 'root_solution' },
  { type: 'textarea', label: '问题验证结果', group: 'scene', key: 'verify_result' },
  { type: 'radio', label: '是否重大问题', group: 'scene', key: 'major_problem' },
  { type: 'textarea', label: '重大问题回顾和改进', group: 'scene', key: 'major_review' },
  { type: 'textarea', label: '问题回顾和改进措施', group: 'scene', key: 'review_action' },
  { type: 'radio', label: '是否已知错误', group: 'scene', key: 'known_error' },
  { type: 'datetime', label: '问题发生时间', group: 'scene', key: 'occur_time' },
  { type: 'datetime', label: '问题解决时间', group: 'scene', key: 'resolve_time' },
  { type: 'select', label: '提单渠道', group: 'scene', key: 'channel', placeholder: '请选择' },
  { type: 'select', label: '优先级', group: 'scene', key: 'priority', placeholder: '请选择' },
];

export const ALL_FIELDS = [...BASIC_FIELDS, ...SENIOR_FIELDS, ...SCENE_FIELDS];

export const fieldLabelId = (item: CatalogField) => `itsm.field.${item.key || item.type}`;

/** 与 ITSM4 ONELINETYPE 一致：只能占满整行。 */
export const FULL_ROW_TYPES = new Set([
  'section',
  'table',
  'nestedTable',
  'task',
  'tab',
  'richtext',
  'subProcessForm',
  'cab',
  'associateConfig',
]);

export const CHOICE_TYPES = new Set(['select', 'radio', 'checkbox', 'multiselect', 'cascade', 'multiCascade']);
export const CASCADE_TYPES = new Set(['cascade', 'multiCascade']);
