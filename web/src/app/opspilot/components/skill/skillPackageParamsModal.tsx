'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Input, Modal, Select, Tooltip } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import EditablePasswordField from '@/components/dynamic-form/editPasswordField';
import {
  SkillPackage,
  SkillPackageParam,
  SkillPackageVariableDecl,
} from '@/app/opspilot/types/skill';

const { TextArea } = Input;
const PARAM_KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

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
      .map((row) => {
        const key = String(row.key || '').trim();
        const type = row.declared ? resolveDeclType(declared.get(row.key)) : normalizeParamType(row.type);
        return {
          key,
          value: row.value || '',
          type,
          multiline: type === 'textarea',
        };
      })
      .filter((row) => row.key);
    const invalid = normalized.find((row) => !PARAM_KEY_RE.test(row.key));
    if (invalid) {
      Modal.error({
        title: t('skill.skillPackageParams.nameRule'),
      });
      return;
    }
    const seen = new Set<string>();
    for (const row of normalized) {
      if (seen.has(row.key)) {
        Modal.error({
          title: t('skill.skillPackageParams.nameRule'),
        });
        return;
      }
      seen.add(row.key);
    }
    onOk(normalized);
  };

  return (
    <Modal
      title={`${t('skill.skillPackageParams.modalTitle')}${pkg?.name ? ` · ${pkg.name}` : ''}`}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      width={780}
      destroyOnClose
    >
      <p className="mb-2 text-xs leading-5 text-[var(--color-text-4)]">{t('skill.skillPackageParams.modalTip')}</p>
      <div className="mb-4 rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2 text-xs leading-5 text-[var(--color-text-3)]">
        {t('skill.skillPackageParams.typeHint')}
      </div>
      <div className="max-h-[480px] overflow-y-auto pr-1">
        {draft.map((row, index) => {
          const decl = row.declared ? declared.get(row.key) : undefined;
          const lockedName = row.declared;
          const lockedDelete = Boolean(decl?.required);
          const paramType = lockedName ? resolveDeclType(decl) : normalizeParamType(row.type);
          const isTextarea = paramType === 'textarea';
          const valuePlaceholder = paramType === 'password'
            ? t('skill.skillPackageParams.passwordPlaceholder')
            : isTextarea
              ? t('skill.skillPackageParams.multilinePlaceholder')
              : t('skill.skillPackageParams.valuePlaceholder');
          return (
            <div
              key={row.uid}
              className={index > 0 ? 'border-t border-[var(--color-border)] pt-3 mt-3' : ''}
            >
              <div className={`flex gap-2 ${isTextarea ? 'items-start' : 'items-center'}`}>
                <div className="w-[168px] min-w-0 shrink-0">
                  {lockedName ? (
                    <div className="flex h-8 items-center text-sm text-[var(--color-text-1)]">
                      {decl?.required ? (
                        <span className="mr-1 font-semibold text-[var(--color-fail)]" aria-hidden>
                          *
                        </span>
                      ) : null}
                      <span className="truncate font-medium">{row.key}</span>
                    </div>
                  ) : (
                    <Input
                      value={row.key}
                      placeholder={t('skill.skillPackageParams.namePlaceholder')}
                      onChange={(event) => updateRow(row.uid, { key: event.target.value })}
                    />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  {isTextarea ? (
                    <TextArea
                      value={row.value}
                      rows={3}
                      placeholder={valuePlaceholder}
                      onChange={(event) => updateRow(row.uid, { value: event.target.value })}
                    />
                  ) : paramType === 'password' ? (
                    <EditablePasswordField
                      size="middle"
                      value={row.value}
                      placeholder={valuePlaceholder}
                      onChange={(value) => updateRow(row.uid, { value })}
                    />
                  ) : (
                    <Input
                      value={row.value}
                      placeholder={valuePlaceholder}
                      onChange={(event) => updateRow(row.uid, { value: event.target.value })}
                    />
                  )}
                </div>
                <Select
                  className="w-[128px] shrink-0"
                  value={paramType}
                  disabled={lockedName}
                  options={[
                    { value: 'text', label: t('skill.skillPackageParams.text') },
                    { value: 'password', label: t('skill.skillPackageParams.password') },
                    { value: 'textarea', label: t('skill.skillPackageParams.textarea') },
                  ]}
                  onChange={(type) => updateRow(row.uid, { type: normalizeParamType(type), value: '' })}
                />
                <div className="flex h-8 w-8 shrink-0 items-center justify-center">
                  <Tooltip title={lockedDelete ? t('skill.skillPackageParams.declaredLocked') : undefined}>
                    <Button
                      type="text"
                      size="small"
                      disabled={lockedDelete}
                      icon={<DeleteOutlined />}
                      aria-label={t('common.delete')}
                      onClick={() => setDraft((prev) => prev.filter((item) => item.uid !== row.uid))}
                    />
                  </Tooltip>
                </div>
              </div>
              {decl?.description ? (
                <p className="mt-1 pl-3 text-xs text-[var(--color-text-4)]">{decl.description}</p>
              ) : null}
              {paramType === 'password' && row.value === '******' ? (
                <p className="mt-1 pl-[176px] text-xs text-[var(--color-text-4)]">
                  {t('skill.skillPackageParams.savedPasswordHint')}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
      <Button
        className="mt-4"
        type="dashed"
        icon={<PlusOutlined />}
        onClick={() => setDraft((prev) => [
          ...prev,
          { uid: nextDraftUid(), declared: false, key: '', value: '', type: 'text', multiline: false },
        ])}
      >
        {t('skill.skillPackageParams.add')}
      </Button>
    </Modal>
  );
};

export default SkillPackageParamsModal;
