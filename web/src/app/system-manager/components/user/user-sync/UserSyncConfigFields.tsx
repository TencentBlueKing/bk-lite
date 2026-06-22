import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Form,
  Input,
  InputNumber,
  Select,
  Spin,
  Switch,
  TreeSelect,
} from 'antd';

import { useUserSyncApi } from '@/app/system-manager/api/user-sync';
import type {
  BusinessTemplate,
  TemplateField,
} from '@/app/system-manager/types/integration-center';
import type { UserSyncDepartmentNode } from '@/app/system-manager/types/user-sync';
import {
  PLATFORM_FIELD_META,
  type MappingRow,
  updateMappingRowField,
} from '@/app/system-manager/utils/userSyncPageUtils';

interface UserSyncConfigFieldsProps {
  selectedInstanceId?: number;
  providersLoading: boolean;
  resolvedTemplate: BusinessTemplate | null;
  mappingRows: MappingRow[];
  t: (key: string, fallback?: string) => string;
  onMappingRowsChange: React.Dispatch<React.SetStateAction<MappingRow[]>>;
  hideRootDepartmentField?: boolean;
}

interface MappingInputRowProps {
  row: MappingRow;
  index: number;
  placeholder: string;
  onChange: (index: number, value: string) => void;
}

const ALL_DEPARTMENT_SELECTION_ID = '__all__';

function toTreeSelectData(nodes: UserSyncDepartmentNode[]): Array<{
  title: string;
  value: string;
  key: string;
  selectable: boolean;
  children?: ReturnType<typeof toTreeSelectData>;
}> {
  return nodes.map((node) => ({
    title: node.name,
    value: node.id,
    key: node.id,
    selectable: node.selectable,
    children: node.children.length > 0 ? toTreeSelectData(node.children) : undefined,
  }));
}

const MappingInputRow = memo(({
  row,
  index,
  placeholder,
  onChange,
}: MappingInputRowProps) => (
  <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4">
    <div className="rounded-sm border border-[var(--color-border)] bg-white p-2">
      <div className="text-[var(--color-text)]">
        {PLATFORM_FIELD_META[row.platformField as keyof typeof PLATFORM_FIELD_META]?.label || row.platformField}
      </div>
    </div>
    <div className="flex items-center justify-center text-[var(--color-primary)]">→</div>
    <Input
      value={row.externalField}
      onChange={(event) => onChange(index, event.target.value)}
      placeholder={placeholder}
    />
  </div>
));

MappingInputRow.displayName = 'MappingInputRow';

const UserSyncConfigFields: React.FC<UserSyncConfigFieldsProps> = ({
  selectedInstanceId,
  providersLoading,
  resolvedTemplate,
  mappingRows,
  t,
  onMappingRowsChange,
  hideRootDepartmentField = false,
}) => {
  const form = Form.useFormInstance();
  const { getDepartmentOptions } = useUserSyncApi();
  const externalFieldPlaceholder = t('system.user.userSyncPage.externalFieldPlaceholder', '默认留空，按需填写外部字段名');
  const watchedDepartmentIdType = Form.useWatch(['business_config', 'department_id_type'], form);
  const watchedRootDepartmentId = Form.useWatch(['business_config', 'root_department_id'], form);
  const departmentIdType = typeof watchedDepartmentIdType === 'string' ? watchedDepartmentIdType : '';
  const currentRootDepartmentId = typeof watchedRootDepartmentId === 'string' ? watchedRootDepartmentId : '';
  const currentRootDepartmentIdRef = useRef(currentRootDepartmentId);
  const [departmentNodes, setDepartmentNodes] = useState<UserSyncDepartmentNode[]>([]);
  const [departmentSelectionMissing, setDepartmentSelectionMissing] = useState(false);
  const [departmentLoadError, setDepartmentLoadError] = useState('');
  const [departmentLoading, setDepartmentLoading] = useState(false);

  const departmentTreeData = useMemo(() => toTreeSelectData(departmentNodes), [departmentNodes]);

  useEffect(() => {
    currentRootDepartmentIdRef.current = currentRootDepartmentId;
  }, [currentRootDepartmentId]);

  const handleMappingRowChange = useCallback((index: number, value: string) => {
    onMappingRowsChange((prevRows) => updateMappingRowField(prevRows, index, value));
  }, [onMappingRowsChange]);

  useEffect(() => {
    let active = true;

    async function fetchDepartmentOptions() {
      if (!selectedInstanceId) {
        setDepartmentNodes([]);
        setDepartmentSelectionMissing(false);
        setDepartmentLoadError('');
        form.setFieldValue(['business_config', 'root_department_id'], undefined);
        form.setFields([{ name: ['business_config', 'root_department_id'], errors: [] }]);
        return;
      }

      setDepartmentLoading(true);
      setDepartmentLoadError('');
      try {
        const result = await getDepartmentOptions({
          integration_instance: selectedInstanceId,
          current_root_department_id: currentRootDepartmentIdRef.current,
          department_id_type: departmentIdType,
        });
        if (!active) return;

        setDepartmentNodes(result.items || []);
        setDepartmentSelectionMissing(result.selection_missing);

        const currentFormValue = String(form.getFieldValue(['business_config', 'root_department_id']) || '');
        const nextValue = result.selection_missing
          ? ''
          : (result.selected_id || currentFormValue || ALL_DEPARTMENT_SELECTION_ID);

        if (nextValue && nextValue !== currentFormValue) {
          form.setFieldValue(['business_config', 'root_department_id'], nextValue);
        } else if (!nextValue && currentFormValue) {
          form.setFieldValue(['business_config', 'root_department_id'], undefined);
        }

        form.setFields([{
          name: ['business_config', 'root_department_id'],
          errors: result.selection_missing ? [t('system.user.userSyncPage.departmentSelectionInvalid')] : [],
        }]);
      } catch {
        if (!active) return;
        setDepartmentNodes([]);
        setDepartmentSelectionMissing(false);
        setDepartmentLoadError(t('system.user.userSyncPage.departmentOptionsLoadFailed'));
        form.setFields([{
          name: ['business_config', 'root_department_id'],
          errors: [t('system.user.userSyncPage.departmentOptionsLoadFailed')],
        }]);
      } finally {
        if (active) {
          setDepartmentLoading(false);
        }
      }
    }

    fetchDepartmentOptions();
    return () => {
      active = false;
    };
  }, [departmentIdType, form, selectedInstanceId, t]);

  const renderManifestField = (field: TemplateField) => {
    if (hideRootDepartmentField && (field.key === 'root_department_id' || field.key === 'department_id_type')) {
      return null;
    }

    const namePath = ['business_config', field.key];
    const rules = field.required
      ? [{ required: true, whitespace: field.field_type === 'string' || field.field_type === 'textarea' }]
      : undefined;
    const placeholder = field.write_only
      ? t('system.integrationCenter.keepSecretPlaceholder', '如无需变更可留空')
      : field.placeholder || undefined;
    const wrapperClassName = field.field_type === 'textarea' ? 'md:col-span-2' : '';

    if (field.key === 'root_department_id') {
      return (
        <div key={field.key} className={wrapperClassName}>
          {departmentSelectionMissing ? (
            <Alert
              className="mb-4"
              message={t('system.user.userSyncPage.departmentSelectionInvalid')}
              type="warning"
              showIcon
            />
          ) : null}
          {departmentLoadError ? (
            <Alert
              className="mb-4"
              message={departmentLoadError}
              type="error"
              showIcon
            />
          ) : null}
          <Form.Item
            name={namePath}
            label={field.label}
            required={field.required}
            rules={[{ required: field.required }]}
          >
            <TreeSelect
              treeData={departmentTreeData}
              treeDefaultExpandAll
              loading={departmentLoading}
              disabled={!selectedInstanceId || !!departmentLoadError}
              placeholder={departmentLoading
                ? t('system.user.userSyncPage.departmentOptionsLoading')
                : t('system.user.userSyncPage.rootDepartmentPlaceholder')}
              onChange={() => {
                form.setFields([{ name: namePath, errors: [] }]);
                setDepartmentSelectionMissing(false);
              }}
            />
          </Form.Item>
        </div>
      );
    }

    switch (field.field_type) {
      case 'textarea':
        return (
          <div key={field.key} className={wrapperClassName}>
            <Form.Item
              name={namePath}
              label={field.label}
              required={field.required}
              rules={rules}
              tooltip={field.help_text || undefined}
            >
              <Input.TextArea rows={4} placeholder={placeholder} />
            </Form.Item>
          </div>
        );
      case 'password':
        return (
          <div key={field.key} className={wrapperClassName}>
            <Form.Item
              name={namePath}
              label={field.label}
              required={field.required}
              rules={rules}
              tooltip={field.help_text || undefined}
            >
              <Input.Password placeholder={placeholder} />
            </Form.Item>
          </div>
        );
      case 'number':
        return (
          <div key={field.key} className={wrapperClassName}>
            <Form.Item
              name={namePath}
              label={field.label}
              required={field.required}
              rules={rules}
              tooltip={field.help_text || undefined}
            >
              <InputNumber className="w-full" placeholder={placeholder} />
            </Form.Item>
          </div>
        );
      case 'boolean':
        return (
          <div key={field.key} className={wrapperClassName}>
            <Form.Item
              name={namePath}
              label={field.label}
              required={field.required}
              tooltip={field.help_text || undefined}
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </div>
        );
      case 'select':
        return (
          <div key={field.key} className={wrapperClassName}>
            <Form.Item
              name={namePath}
              label={field.label}
              required={field.required}
              rules={rules}
              tooltip={field.help_text || undefined}
            >
              <Select
                options={field.options.map((opt) => ({
                  value: opt.value as string | number | boolean,
                  label: String(opt.label),
                }))}
                placeholder={placeholder}
              />
            </Form.Item>
          </div>
        );
      default:
        return (
          <div key={field.key} className={wrapperClassName}>
            <Form.Item
              name={namePath}
              label={field.label}
              required={field.required}
              rules={rules}
              tooltip={field.help_text || undefined}
            >
              <Input placeholder={placeholder} />
            </Form.Item>
          </div>
        );
    }
  };

  return (
    <>
      <div className="mb-2 font-semibold">{t('system.user.userSyncPage.accessConfig')}</div>
      <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
        {t('system.user.userSyncPage.accessHint')}
      </div>
      {selectedInstanceId ? (
        providersLoading ? (
          <div className="flex items-center justify-center py-4">
            <Spin spinning size="small" />
          </div>
        ) : resolvedTemplate ? (
          resolvedTemplate.groups.map((group) => {
            if (group.fields.length === 0) return null;
            return (
              <div key={group.key} className="mb-2">
                {group.title ? (
                  <div className="mb-3 mt-1 text-[14px] font-medium text-[var(--color-text-2)]">{group.title}</div>
                ) : null}
                <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
                  {group.fields.map((field) => renderManifestField(field))}
                </div>
              </div>
            );
          })
        ) : (
          <Alert
            type="warning"
            showIcon
            className="mb-4"
            message={t('system.user.userSyncPage.manifestNotFound')}
          />
        )
      ) : null}
      <div className="mt-6 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
        <div className="mb-4 font-semibold">{t('system.user.userSyncPage.fieldMappingTitle')}</div>
        <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 gap-y-3 text-[13px] text-[var(--color-text-3)]">
          <div>{t('system.user.userSyncPage.platformFieldColumn')}</div>
          <div />
          <div>{t('system.user.userSyncPage.externalFieldColumn')}</div>
        </div>
        <div className="mt-3 space-y-3">
          {mappingRows.map((row, index) => (
            <MappingInputRow
              key={row.platformField}
              row={row}
              index={index}
              placeholder={externalFieldPlaceholder}
              onChange={handleMappingRowChange}
            />
          ))}
        </div>
        {resolvedTemplate?.available_external_fields && resolvedTemplate.available_external_fields.length > 0 ? (
          <div className="mt-3 rounded-xl bg-[var(--color-bg)] px-3 py-2 text-[12px] text-[var(--color-text-3)]">
            {t('system.user.userSyncPage.externalFieldsHint')}
            {resolvedTemplate.available_external_fields.join('、')}
          </div>
        ) : null}
      </div>
    </>
  );
};

export default UserSyncConfigFields;
