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
import { useChannelApi } from '@/app/system-manager/api/channel';
import type {
  BusinessTemplate,
  TemplateField,
} from '@/app/system-manager/types/integration-center';
import type { UserSyncDepartmentNode } from '@/app/system-manager/types/user-sync';
import PasswordInitSection from '@/app/system-manager/components/user/user-sync/PasswordInitSection';
import {
  getEffectiveRootDepartmentFieldKey,
  getRootDepartmentInputMode,
  shouldFetchDepartmentOptions,
} from '@/app/system-manager/utils/userSyncUtils';
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
  mappingError?: string;
  hideRootDepartmentField?: boolean;
  rootScopeField?: string;
}

interface MappingInputRowProps {
  row: MappingRow;
  index: number;
  placeholder: string;
  required?: boolean;
  invalid?: boolean;
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
  required = false,
  invalid = false,
  onChange,
}: MappingInputRowProps) => (
  <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4">
    <div className="rounded-sm border border-[var(--color-border)] bg-white p-2">
      <div className="text-[var(--color-text)]">
        {PLATFORM_FIELD_META[row.platformField as keyof typeof PLATFORM_FIELD_META]?.label || row.platformField}
        {required ? <span className="ml-1 text-[var(--color-error)]">*</span> : null}
      </div>
    </div>
    <div className="flex items-center justify-center text-[var(--color-primary)]">→</div>
    <div>
      <Input
        value={row.externalField}
        onChange={(event) => onChange(index, event.target.value)}
        placeholder={placeholder}
        status={invalid ? 'error' : undefined}
      />
    </div>
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
  mappingError,
  hideRootDepartmentField = false,
  rootScopeField,
}) => {
  const form = Form.useFormInstance();
  const { getDepartmentOptions } = useUserSyncApi();
  const { getChannelData } = useChannelApi();
  const [emailChannels, setEmailChannels] = useState<
    { id: number; name: string }[]
  >([]);
  const fetchedRef = useRef(false);

  // 整个 UserSyncConfigFields 生命周期内仅 fetch 一次邮件 channel 列表。
  // 用 ref 锁住 (而非 deps) 避免 useChannelApi 每次返回新引用触发无限循环。
  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    (async () => {
      try {
        const resp = await getChannelData({});
        const items: any[] = Array.isArray(resp)
          ? resp
          : Array.isArray((resp as any)?.items)
            ? (resp as any).items
            : Array.isArray((resp as any)?.results)
              ? (resp as any).results
              : [];
        const opts = items
          .filter((c: any) => c?.channel_type === 'email')
          .map((c: any) => ({
            id: typeof c.id === 'number' ? c.id : Number(c.id),
            name: c.name ?? '(未命名)',
          }))
          .filter((o) => !Number.isNaN(o.id));
        // 注释：React 18 dev strict mode 会 mount → cleanup → mount,cleanup 中设 cancelled=true 会让 async 跳过 setState.
        // 取消 cleanup 不再设取消标志,直接在 setEmailChannels 后判断 Unmounted.
        // 但更好做法是 setEmailChannels 总是执行,这样重复 mount 时会重置。fetchedRef 已是 ref,无法重置。
        if (typeof window !== 'undefined') {
          setEmailChannels((prev) => (prev.length === 0 ? opts : prev));
        }
      } catch {
        setEmailChannels([]);
      }
    })();
    // 空 cleanup:React 18 dev 双调用由 fetchedRef 锁住
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const externalFieldPlaceholder = t('system.user.userSyncPage.externalFieldPlaceholder');
  const watchedDepartmentIdType = Form.useWatch(['business_config', 'department_id_type'], form);
  const departmentIdType = typeof watchedDepartmentIdType === 'string' ? watchedDepartmentIdType : '';
  const [departmentNodes, setDepartmentNodes] = useState<UserSyncDepartmentNode[]>([]);
  const [departmentSelectionMissing, setDepartmentSelectionMissing] = useState(false);
  const [departmentLoadError, setDepartmentLoadError] = useState('');
  const [departmentLoading, setDepartmentLoading] = useState(false);

  const departmentTreeData = useMemo(() => toTreeSelectData(departmentNodes), [departmentNodes]);
  const rootDepartmentFieldKey = useMemo(
    () => getEffectiveRootDepartmentFieldKey({ root_scope_field: rootScopeField }, resolvedTemplate),
    [resolvedTemplate, rootScopeField],
  );
  const inputMode = useMemo(() => getRootDepartmentInputMode(resolvedTemplate), [resolvedTemplate]);
  const watchedRootDepartmentValue = Form.useWatch(['business_config', rootDepartmentFieldKey], form);
  const currentRootDepartmentId = typeof watchedRootDepartmentValue === 'string' ? watchedRootDepartmentValue : '';
  const currentRootDepartmentIdRef = useRef(currentRootDepartmentId);

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
        form.setFieldValue(['business_config', rootDepartmentFieldKey], undefined);
        form.setFields([{ name: ['business_config', rootDepartmentFieldKey], errors: [] }]);
        return;
      }

      if (!shouldFetchDepartmentOptions({ selectedInstanceId, template: resolvedTemplate })) {
        setDepartmentNodes([]);
        setDepartmentSelectionMissing(false);
        setDepartmentLoadError('');
        setDepartmentLoading(false);
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

        const currentFormValue = String(form.getFieldValue(['business_config', rootDepartmentFieldKey]) || '');
        const nextValue = result.selection_missing
          ? ''
          : (result.selected_id || currentFormValue || ALL_DEPARTMENT_SELECTION_ID);

        if (nextValue && nextValue !== currentFormValue) {
          form.setFieldValue(['business_config', rootDepartmentFieldKey], nextValue);
        } else if (!nextValue && currentFormValue) {
          form.setFieldValue(['business_config', rootDepartmentFieldKey], undefined);
        }

        form.setFields([{
          name: ['business_config', rootDepartmentFieldKey],
          errors: result.selection_missing ? [t('system.user.userSyncPage.departmentSelectionInvalid')] : [],
        }]);
      } catch {
        if (!active) return;
        setDepartmentNodes([]);
        setDepartmentSelectionMissing(false);
        setDepartmentLoadError(t('system.user.userSyncPage.departmentOptionsLoadFailed'));
        form.setFields([{
          name: ['business_config', rootDepartmentFieldKey],
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
  }, [departmentIdType, form, resolvedTemplate, rootDepartmentFieldKey, selectedInstanceId, t]);

  const renderManifestField = (field: TemplateField) => {
    if (hideRootDepartmentField && (field.key === rootDepartmentFieldKey || field.key === 'department_id_type')) {
      return null;
    }

    const namePath = ['business_config', field.key];
    const rules = field.required
      ? [{ required: true, whitespace: field.field_type === 'string' || field.field_type === 'textarea' }]
      : undefined;
    const placeholder = field.write_only
      ? t('system.integrationCenter.keepSecretPlaceholder')
      : field.placeholder || undefined;
    const wrapperClassName = field.field_type === 'textarea' ? 'md:col-span-2' : '';

    if (field.key === rootDepartmentFieldKey) {
      if (inputMode === 'manual_input') {
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
      {/* 本地密码初始化(每个同步源独立配置;与 manifest 字段并列) */}
      <PasswordInitSection emailChannels={emailChannels ?? []} t={t} />
      <div className="mt-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
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
              required={row.platformField === 'username'}
              invalid={row.platformField === 'username' && Boolean(mappingError)}
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
