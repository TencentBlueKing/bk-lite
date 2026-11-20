import type { CSSProperties, ReactNode } from 'react';

export interface FormFieldRowGroup {
  rowKey: string | null;
  fields: any[];
}

export const FormFieldRow = ({
  rowKey,
  fields,
  width,
  renderField
}: {
  rowKey: string;
  fields: any[];
  width: number;
  renderField: (field: any) => ReactNode;
}) => (
  <div
    data-form-row={rowKey}
    className="flex flex-nowrap items-start gap-x-6"
  >
    {fields.map((field) => (
      <div
        key={field?.name || rowKey}
        className="max-w-full shrink-0"
        style={{ width } as CSSProperties}
      >
        {renderField(field)}
      </div>
    ))}
  </div>
);

const rowKeyOf = (field: any) =>
  typeof field?.row === 'string' ? field.row.trim() : '';

/** 连续且 row 相同的字段排成同一行；单独一个 row 仍按原样独占一行。 */
export const groupFormFieldsIntoRows = (
  fields: any[] | null | undefined
): FormFieldRowGroup[] => {
  const groups: FormFieldRowGroup[] = [];
  const list = fields || [];
  for (let index = 0; index < list.length; index += 1) {
    const field = list[index];
    const rowKey = rowKeyOf(field);
    if (rowKey) {
      const grouped = [field];
      while (index + 1 < list.length && rowKeyOf(list[index + 1]) === rowKey) {
        index += 1;
        grouped.push(list[index]);
      }
      if (grouped.length > 1) {
        groups.push({ rowKey, fields: grouped });
        continue;
      }
    }
    groups.push({ rowKey: null, fields: [field] });
  }
  return groups;
};
