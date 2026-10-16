'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Input, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import {
  SkillPackage,
  SkillPackageParam,
  SkillPackageVariableDecl,
} from '@/app/opspilot/types/skill';

const { TextArea } = Input;

const isFilled = (item?: SkillPackageParam) => Boolean(item?.key && String(item.value || '').trim());

export const resolveDeclType = (decl?: SkillPackageVariableDecl | null): SkillPackageParam['type'] => {
  const declaredType = String(decl?.type || '').trim().toLowerCase();
  if (declaredType === 'password' || declaredType === 'textarea' || declaredType === 'text') {
    return declaredType;
  }
  if (decl?.secret) return 'password';
  const input = String(decl?.input || '').trim().toLowerCase();
  if (input === 'textarea' || decl?.multiline) return 'textarea';
  return 'text';
};

export const normalizeParamType = (type?: string): SkillPackageParam['type'] => {
  if (type === 'password' || type === 'textarea') return type;
  return 'text';
};

const asVariableDeclList = (raw: unknown): SkillPackageVariableDecl[] => {
  if (!Array.isArray(raw)) return [];
  const result: SkillPackageVariableDecl[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const row = item as SkillPackageVariableDecl & { key?: string };
    const name = String(row.name || row.key || '').trim();
    if (!name) continue;
    result.push({ ...row, name });
  }
  return result;
};

/** 声明预读：优先顶层 variables，回退 manifest.variables（兼容旧列表响应 / 热更新未带 SerializerMethodField）。 */
export const resolvePackageVariables = (pkg?: SkillPackage | null): SkillPackageVariableDecl[] => {
  const top = asVariableDeclList(pkg?.variables);
  if (top.length) return top;
  const fromManifest = pkg?.manifest && typeof pkg.manifest === 'object'
    ? asVariableDeclList((pkg.manifest as { variables?: unknown }).variables)
    : [];
  return fromManifest;
};

export const withResolvedVariables = (pkg: SkillPackage): SkillPackage => ({
  ...pkg,
  variables: resolvePackageVariables(pkg),
});

/** 技能包只有声明了变量才需要打开配置；未声明时没有可填参数。 */
export const packageHasDeclaredParams = (pkg?: SkillPackage | null) => resolvePackageVariables(pkg).length > 0;

export const getDeclaredMap = (pkg?: SkillPackage | null) => {
  const map = new Map<string, SkillPackageVariableDecl>();
  for (const decl of resolvePackageVariables(pkg)) {
    map.set(decl.name, decl);
  }
  return map;
};

export const mergeDeclaredParams = (
  pkg: SkillPackage | null | undefined,
  items: SkillPackageParam[] | undefined,
): SkillPackageParam[] => {
  const declared = getDeclaredMap(pkg);
  const existing = new Map((items || []).filter((item) => item?.key).map((item) => [item.key, item]));
  const merged: SkillPackageParam[] = [];
  declared.forEach((decl, name) => {
    const current = existing.get(name);
    const paramType = resolveDeclType(decl);
    merged.push({
      key: name,
      value: current?.value || '',
      type: paramType,
      multiline: paramType === 'textarea',
    });
    existing.delete(name);
  });
  existing.forEach((item) => {
    const type = normalizeParamType(item.type);
    merged.push({ ...item, type, multiline: type === 'textarea' });
  });
  return merged;
};

export const listMissingRequiredParams = (pkg: SkillPackage | null | undefined, items: SkillPackageParam[] | undefined) => {
  const byKey = new Map((items || []).map((item) => [item.key, item]));
  return resolvePackageVariables(pkg)
    .filter((decl) => decl?.required && String(decl.name || '').trim() && !isFilled(byKey.get(decl.name)))
    .map((decl) => decl.name);
};

export const countFilledParams = (items: SkillPackageParam[] | undefined) => (items || []).filter(isFilled).length;

interface DraftRow extends SkillPackageParam {
  uid: string;
  declared: boolean;
}

let draftUid = 0;
const nextDraftUid = () => `skill-param-${++draftUid}`;

const ValueControl = ({
  type,
  value,
  placeholder,
  onChange,
}: {
  type: SkillPackageParam['type'];
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
}) => {
  if (type === 'textarea') {
    return (
      <TextArea
        value={value}
        rows={2}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }
  if (type === 'password') {
    return (
      <EditablePasswordField
        size="middle"
        value={value}
        placeholder={placeholder}
        onChange={onChange}
      />
    );
  }
  return (
    <Input
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  );
};

interface SkillPackageParamsModalProps {
  open: boolean;
  pkg: SkillPackage | null;
  items: SkillPackageParam[];
  onCancel: () => void;
  onOk: (items: SkillPackageParam[]) => void;
}

const SkillPackageParamsModal: React.FC<SkillPackageParamsModalProps> = ({
  open,
  pkg,
  items,
  onCancel,
  onOk,
}) => {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<DraftRow[]>([]);
  const declared = useMemo(() => getDeclaredMap(pkg), [pkg]);

  useEffect(() => {
    if (!open) return;
    const declaredNames = getDeclaredMap(pkg);
    setDraft(
      mergeDeclaredParams(pkg, items).map((item) => ({
        ...item,
        uid: nextDraftUid(),
        declared: declaredNames.has(item.key),
      })),
    );
    // 只在打开 / 切换包时重载；不要依赖 items 引用（父级 `|| []` 每次 render 都会变，会打断编辑）。
  }, [open, pkg?.id, pkg?.package_id]);

  const updateRow = (uid: string, patch: Partial<SkillPackageParam>) => {
    setDraft((prev) => prev.map((row) => (row.uid === uid ? { ...row, ...patch } : row)));
  };

  const handleOk = () => {
    const normalized = draft
      .filter((row) => row.declared)
      .map((row) => {
        const key = String(row.key || '').trim();
        const type = resolveDeclType(declared.get(row.key));
        return {
          key,
          value: row.value || '',
          type,
          multiline: type === 'textarea',
        };
      })
      .filter((row) => row.key);
    const keptCustom = (items || [])
      .filter((item) => item?.key && !declared.has(item.key))
      .map((item) => {
        const type = normalizeParamType(item.type);
        return {
          key: item.key,
          value: item.value || '',
          type,
          multiline: type === 'textarea',
        };
      });
    onOk([...normalized, ...keptCustom]);
  };

  const declaredRows = draft.filter((row) => row.declared);
  const requiredRows = declaredRows.filter((row) => declared.get(row.key)?.required);
  const missingRequiredCount = requiredRows.filter((row) => !isFilled(row)).length;

  const valuePlaceholderOf = (type: SkillPackageParam['type']) => {
    if (type === 'password') return t('skill.skillPackageParams.passwordPlaceholder');
    if (type === 'textarea') return t('skill.skillPackageParams.multilinePlaceholder');
    return t('skill.skillPackageParams.valuePlaceholder');
  };

  const footerStatus = requiredRows.length === 0
    ? ''
    : missingRequiredCount > 0
      ? t('skill.skillPackageParams.footerMissingRequired', '还有 {count} 项必填未填', { count: missingRequiredCount })
      : t('skill.skillPackageParams.footerRequiredDone', '必填已全部填写');

  return (
    <OperateModal
      title={t('skill.skillPackageParams.modalTitle')}
      subTitle={pkg?.display_name || pkg?.name}
      open={open}
      onCancel={onCancel}
      width={720}
      destroyOnClose
      footer={
        <div className="flex w-full items-center justify-between">
          <div className={`text-xs ${missingRequiredCount > 0 ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-3)]'}`}>
            {footerStatus}
          </div>
          <Space>
            <Button onClick={onCancel}>{t('common.cancel')}</Button>
            <Button type="primary" onClick={handleOk}>{t('common.confirm')}</Button>
          </Space>
        </div>
      }
    >
      <p className="mb-4 mt-0 text-xs leading-5 text-[var(--color-text-3)]">
        {t('skill.skillPackageParams.modalTip')}
      </p>

      <div className="max-h-[440px] space-y-5 overflow-y-auto pr-1">
        {declaredRows.length > 0 && (
          <section>
            <div className="mb-1 text-[13px] font-medium text-[var(--color-text-1)]">
              {t('skill.skillPackageParams.declaredSection', '技能包声明')}
            </div>
            <div className="divide-y divide-[var(--color-fill-2)]">
              {declaredRows.map((row) => {
                const decl = declared.get(row.key);
                const paramType = resolveDeclType(decl);
                return (
                  <div key={row.uid} className="flex items-start gap-4 py-3">
                    <div className="w-[168px] shrink-0 pt-1">
                      <div className="flex min-w-0 items-center gap-1.5">
                        <span className="truncate font-mono text-[13px] font-medium text-[var(--color-text-1)]" title={row.key}>
                          {row.key}
                        </span>
                        {decl?.required ? (
                          <span className="shrink-0 text-[11px] text-[var(--color-fail)]">
                            {t('skill.skillPackageParams.required')}
                          </span>
                        ) : null}
                      </div>
                      {decl?.description ? (
                        <p className="mb-0 mt-1 text-xs leading-5 text-[var(--color-text-4)]">
                          {decl.description}
                        </p>
                      ) : null}
                    </div>
                    <div className="min-w-0 flex-1">
                      <ValueControl
                        type={paramType}
                        value={row.value}
                        placeholder={valuePlaceholderOf(paramType)}
                        onChange={(value) => updateRow(row.uid, { value })}
                      />
                      {paramType === 'password' && row.value === '******' ? (
                        <p className="mb-0 mt-1 text-xs leading-5 text-[var(--color-text-4)]">
                          {t('skill.skillPackageParams.savedPasswordHint')}
                        </p>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

      </div>
    </OperateModal>
  );
};

export default SkillPackageParamsModal;
