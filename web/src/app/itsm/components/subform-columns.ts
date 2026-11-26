import type { FormFieldSchema } from '../types';

export function subformColumns(field: FormFieldSchema): FormFieldSchema[] {
  return field.children && (field.children.length || !field.props?.columns) ? field.children
    : String(field.props?.columns || '名称:name\n数量:quantity:number').split('\n').filter(Boolean).map((line) => {
      const [label, key = label, type = 'input'] = line.split(':');
      return { key: key.trim(), label: label.trim(), type };
    });
}
