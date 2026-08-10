import type { FormInstance } from 'antd';

/**
 * 将表单恢复为「未触摸」状态，但不改动当前值。
 *
 * rc-field-form 2.x（antd 5 依赖）在 `setFieldsValue` 时会把已挂载字段标为
 * touched。组件配置等弹框在打开时用 `setFieldsValue` 回填，随后若用
 * `isFieldsTouched()` 做未保存判断，会出现「未编辑也提示放弃修改」的误报。
 */
export const markFormPristine = (form: FormInstance): void => {
  const names = form.getFieldsError().map((field) => field.name);
  if (names.length === 0) {
    return;
  }
  form.setFields(names.map((name) => ({ name, touched: false })));
};
