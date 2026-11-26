'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Form, Radio, Spin, message } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';
import OperateModal from '@/components/operate-modal';
import { useUserInfoContext } from '@/context/userInfo';
import { useTranslation } from '@/utils/i18n';
import useJobApi from '@/app/job/api';
import type { BatchResource, OrganizationOperation, OrganizationPreview } from '@/app/job/types';

type PreviewState =
  | { status: 'idle' | 'loading' | 'error' }
  | { status: 'ready' | 'submitting'; result: OrganizationPreview };

interface AdjustOrganizationsModalProps {
  resource: BatchResource;
  ids: number[];
  onCancel: () => void;
  onSuccess: () => void;
}

export default function AdjustOrganizationsModal({ resource, ids, onCancel, onSuccess }: AdjustOrganizationsModalProps) {
  const { t } = useTranslation();
  const { flatGroups } = useUserInfoContext();
  const { adjustOrganizations } = useJobApi();
  const resourceName = t(`job.targetOrganizations.resource.${resource}`);
  const [operation, setOperation] = useState<OrganizationOperation>('add');
  const [organization, setOrganization] = useState<number>();
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle' });
  const [excludeBlocked, setExcludeBlocked] = useState(false);
  const latestRequest = useRef(0);
  useEffect(() => () => { latestRequest.current += 1; }, []);

  async function loadPreview(nextOperation: OrganizationOperation, nextOrganization?: number) {
    const request = ++latestRequest.current;
    setOperation(nextOperation);
    setOrganization(nextOrganization);
    setExcludeBlocked(false);
    if (nextOrganization === undefined) {
      setPreview({ status: 'idle' });
      return;
    }
    setPreview({ status: 'loading' });
    try {
      const result = await adjustOrganizations(resource, { ids, operation: nextOperation, organization: nextOrganization });
      if (request === latestRequest.current) setPreview({ status: 'ready', result });
    } catch {
      if (request === latestRequest.current) setPreview({ status: 'error' });
    }
  }

  const result = 'result' in preview ? preview.result : undefined;
  const submitting = preview.status === 'submitting';
  const canSubmit = preview.status === 'ready' && preview.result.changed > 0 &&
    (!preview.result.blocked.length || excludeBlocked);
  const organizationNames = new Map(flatGroups.map(group => [Number(group.id), group.name]));
  const orgName = (id: number) => organizationNames.get(id) ?? String(id);

  async function submit() {
    if (!canSubmit || organization === undefined || preview.status !== 'ready') return;
    const request = ++latestRequest.current;
    setPreview({ status: 'submitting', result: preview.result });
    try {
      const applied = await adjustOrganizations(resource, {
        ids, operation, organization, preview_token: preview.result.preview_token, exclude_blocked: excludeBlocked,
      });
      if (request !== latestRequest.current) return;
      message.success(t('job.targetOrganizations.success', '', {
        changed: applied.changed, unchanged: applied.unchanged, excluded: applied.blocked.length, resource: resourceName,
      }));
      onSuccess();
    } catch {
      if (request === latestRequest.current) {
        setExcludeBlocked(false);
        setPreview({ status: 'error' });
      }
    }
  }

  return (
    <OperateModal
      open
      title={t('job.targetOrganizations.title')}
      subTitle={t('job.targetOrganizations.selected', '', { count: ids.length, resource: resourceName })}
      width={600}
      onCancel={onCancel}
      closable={!submitting}
      keyboard={!submitting}
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button disabled={submitting} onClick={onCancel}>{t('common.cancel')}</Button>
          <Button type="primary" disabled={!canSubmit} loading={submitting} onClick={submit}>
            {organization !== undefined && result
              ? t(operation === 'add' ? 'job.targetOrganizations.applyAdd' : 'job.targetOrganizations.applyRemove', '', {
                count: result.changed, resource: resourceName, org: orgName(organization),
              })
              : t('common.confirm')}
          </Button>
        </div>
      }
    >
      <Form layout="vertical">
        <Form.Item label={t('job.operation')}>
          <Radio.Group
            value={operation}
            disabled={submitting}
            options={[
              { label: t('job.targetOrganizations.add'), value: 'add' },
              { label: t('job.targetOrganizations.remove'), value: 'remove' },
            ]}
            optionType="button"
            onChange={event => loadPreview(event.target.value, organization)}
          />
        </Form.Item>
        <Form.Item label={t('job.organization')}>
          <GroupTreeSelect
            multiple={false}
            showSearch
            allowClear
            disabled={submitting}
            placeholder={t('job.organizationPlaceholder')}
            value={organization}
            onChange={value => loadPreview(operation, Array.isArray(value) ? value[0] : value)}
          />
        </Form.Item>
      </Form>
      <div className="flex flex-col gap-3" aria-live="polite">
        {preview.status === 'loading' && <Spin size="small" />}
        {preview.status === 'error' && (
          <Alert type="warning" showIcon message={t('job.targetOrganizations.previewFailed')}
            action={<Button size="small" onClick={() => loadPreview(operation, organization)}>{t('job.targetOrganizations.retry')}</Button>}
          />
        )}
        {result && (
          <>
            <div>{t(operation === 'add' ? 'job.targetOrganizations.addSummary' : 'job.targetOrganizations.removeSummary', '', {
              changed: result.changed, unchanged: result.unchanged,
            })}</div>
            {result.blocked.length > 0 && (
              <Alert type="warning" showIcon message={t('job.targetOrganizations.lastOrganization', '', { count: result.blocked.length, resource: resourceName })}
                description={
                  <div className="flex flex-col gap-2">
                    <details>
                      <summary className="cursor-pointer">{t('job.targetOrganizations.blockedNames', '', { count: result.blocked.length, resource: resourceName })}</summary>
                      <ul className="mt-1 max-h-40 overflow-y-auto">
                        {result.blocked.map(item => <li key={item.id}>{item.name}</li>)}
                      </ul>
                    </details>
                    <Checkbox checked={excludeBlocked} disabled={submitting} onChange={event => setExcludeBlocked(event.target.checked)}>
                      {t('job.targetOrganizations.excludeBlocked', '', { count: result.blocked.length, resource: resourceName })}
                    </Checkbox>
                  </div>
                }
              />
            )}
            <details>
              <summary className="cursor-pointer text-[var(--color-text-3)]">{t('job.targetOrganizations.details')}</summary>
              <table className="mt-2 w-full text-left text-sm">
                <thead><tr>
                  <th>{t('job.targetOrganizations.before')}</th><th>{t('job.targetOrganizations.after')}</th><th>{t('job.targetOrganizations.count')}</th>
                </tr></thead>
                <tbody>{result.groups.map(group => (
                  <tr key={group.before.join(',')}>
                    <td>{group.before.map(orgName).join(', ') || t('job.targetOrganizations.none')}</td>
                    <td>{group.after.length ? group.after.map(orgName).join(', ') : (
                      group.before.length && operation === 'remove'
                        ? t(excludeBlocked ? 'job.targetOrganizations.keepOriginal' : 'job.targetOrganizations.pending')
                        : t('job.targetOrganizations.none')
                    )}</td>
                    <td>{group.count}</td>
                  </tr>
                ))}</tbody>
              </table>
            </details>
          </>
        )}
      </div>
    </OperateModal>
  );
}
