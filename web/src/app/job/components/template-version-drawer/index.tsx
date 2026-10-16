'use client';

import React, { useEffect, useState } from 'react';
import { Alert, Button, Popconfirm, Table, Tag, Tooltip, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import ReactDiffViewer from 'react-diff-viewer-continued';
import useJobApi from '@/app/job/api';
import OperateDrawer from '@/components/operate-drawer';
import Permission from '@/components/permission';
import {
  PlaybookRevisionCompare,
  ScriptRevisionCompare,
  TemplateFieldDiff,
  TemplateFileDiff,
  TemplateParamDiff,
  TemplateRevision,
} from '@/app/job/types';
import { useTranslation } from '@/utils/i18n';

type RevisionKind = 'script' | 'playbook';
type CompareResult = ScriptRevisionCompare | PlaybookRevisionCompare;

interface TemplateVersionDrawerProps {
  open: boolean;
  kind: RevisionKind;
  targetId: number | null;
  onClose: () => void;
  onRestored: () => void;
}

const formatTime = (timeStr: string) => {
  if (!timeStr) return '-';
  const date = new Date(timeStr);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

const isPlaybookCompare = (value: CompareResult): value is PlaybookRevisionCompare => 'files' in value;

const formatByteSize = (size: number | null) => {
  if (size == null) return '--';
  if (size < 1024) return `${size} B`;
  const kb = size / 1024;
  const text = kb >= 10 ? String(Math.round(kb)) : kb.toFixed(1).replace(/\.0$/, '');
  return `${text} KB`;
};

const TemplateVersionDrawer: React.FC<TemplateVersionDrawerProps> = ({
  open,
  kind,
  targetId,
  onClose,
  onRestored,
}) => {
  const { t } = useTranslation();
  const {
    getScriptRevisions,
    compareScriptRevision,
    restoreScriptRevision,
    getPlaybookRevisions,
    comparePlaybookRevision,
    restorePlaybookRevision,
  } = useJobApi();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<TemplateRevision[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const pageSize = 50;

  const fieldLabel = (key: string) => {
    if (key === 'name') return kind === 'script' ? t('job.scriptName') : t('job.playbookName');
    if (key === 'description') return kind === 'script' ? t('job.scriptDescription') : t('job.playbookDescription');
    if (key === 'script_type') return t('job.scriptType');
    if (key === 'timeout') return t('job.timeout');
    if (key === 'version') return t('job.version');
    return key;
  };

  const statusLabel = (status: string) => {
    if (status === 'added') return t('job.diffAdded');
    if (status === 'removed') return t('job.diffRemoved');
    if (status === 'modified') return t('job.diffModified');
    return t('job.diffUnchanged');
  };

  const load = async (nextPage = page) => {
    if (!targetId) return;
    setLoading(true);
    try {
      const response = kind === 'script'
        ? await getScriptRevisions(targetId, { page: nextPage, page_size: pageSize })
        : await getPlaybookRevisions(targetId, { page: nextPage, page_size: pageSize });
      setItems(response.items || []);
      setTotal(response.count || 0);
      setPage(nextPage);
    } catch {
      // 接口失败由全局请求拦截器提示
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open || !targetId) return;
    setCompare(null);
    setSelectedFile('');
    load(1);
  }, [open, targetId, kind]);

  const openCompare = async (revision: TemplateRevision) => {
    if (!targetId) return;
    setCompareLoading(true);
    try {
      const response = kind === 'script'
        ? await compareScriptRevision(targetId, revision.id)
        : await comparePlaybookRevision(targetId, revision.id);
      setCompare(response);
      setSelectedFile('');
    } catch {
      // 接口失败由全局请求拦截器提示
    } finally {
      setCompareLoading(false);
    }
  };

  const restore = async (revision: TemplateRevision) => {
    if (!targetId) return;
    try {
      if (kind === 'script') {
        await restoreScriptRevision(targetId, revision.id);
      } else {
        await restorePlaybookRevision(targetId, revision.id);
      }
      message.success(t('job.versionRestored').replace('{label}', revision.label));
      setCompare(null);
      await load(1);
      onRestored();
    } catch {
      // 接口失败由全局请求拦截器提示
    }
  };

  const columns: ColumnsType<TemplateRevision> = [
    {
      title: t('job.version'),
      dataIndex: 'label',
      render: (label: string, record) => (
        <span className="inline-flex items-center gap-2">
          {label}
          {record.is_current ? <Tag color="blue">{t('job.currentTag')}</Tag> : null}
        </span>
      ),
    },
    {
      title: t('job.updateTime'),
      dataIndex: 'created_at',
      render: (value: string) => formatTime(value),
    },
    {
      title: t('job.versionOperator'),
      dataIndex: 'created_by',
      render: (value: string) => value || '--',
    },
    {
      title: t('job.operation'),
      width: 140,
      render: (_value, record) => (
        <div className="flex items-center gap-3">
          <Tooltip title={t('job.compareWithCurrent')}>
            <a className="cursor-pointer text-[var(--color-primary)]" onClick={() => openCompare(record)}>
              {t('job.compare')}
            </a>
          </Tooltip>
          {record.is_current ? (
            <Tooltip title={t('job.alreadyCurrentVersion')}>
              <span className="cursor-not-allowed text-[var(--color-text-4)]">{t('job.restore')}</span>
            </Tooltip>
          ) : (
            <Permission requiredPermissions={['Edit']}>
              <Tooltip title={t('job.restoreThisVersion')}>
                <Popconfirm
                  title={t('job.restoreThisVersion')}
                  description={t('job.restoreVersionConfirm')}
                  okText={t('job.confirm')}
                  cancelText={t('job.cancel')}
                  onConfirm={() => restore(record)}
                >
                  <a className="cursor-pointer text-[var(--color-primary)]">{t('job.restore')}</a>
                </Popconfirm>
              </Tooltip>
            </Permission>
          )}
        </div>
      ),
    },
  ];

  const changedFields = (compare?.fields || []).filter((field) => field.changed);
  const activeFile = compare && isPlaybookCompare(compare)
    ? compare.files.find((file) => file.path === selectedFile)
    : undefined;

  return (
    <OperateDrawer
      title={t('job.versionHistory')}
      width={960}
      open={open}
      onClose={onClose}
      destroyOnHidden
      styles={{ body: { overflow: 'auto' } }}
    >
      <Alert className="mb-4" type="info" showIcon message={t('job.restoreVersionEffect')} />
      {compare ? (
        <div className="flex flex-col gap-4">
          <Button className="self-start" onClick={() => { setCompare(null); setSelectedFile(''); }}>{t('job.backToVersions')}</Button>
          <div className="text-sm text-[var(--color-text-2)]">
            {compare.selected.label} / {compare.current.label}
          </div>
          {compare.selected.id === compare.current.id ? (
            <Alert type="info" showIcon message={t('job.currentVersionCompareHint')} />
          ) : null}
          {changedFields.length > 0 && (
            <FieldChanges fields={changedFields} labelOf={fieldLabel} />
          )}
          {compare && !isPlaybookCompare(compare) && (
            <DiffBlock
              title={t('job.scriptContentDiff')}
              selectedLabel={compare.selected.label}
              currentLabel={compare.current.label}
              selected={compare.content.selected}
              current={compare.content.current}
            />
          )}
          {compare && isPlaybookCompare(compare) && (
            <DiffBlock
              title={t('job.readmeDiff')}
              selectedLabel={compare.selected.label}
              currentLabel={compare.current.label}
              selected={compare.readme.selected}
              current={compare.readme.current}
            />
          )}
          <ParamChanges params={compare.params} statusLabel={statusLabel} t={t} />
          {compare && isPlaybookCompare(compare) && (
            <FileChanges
              files={compare.files}
              archiveError={compare.archive_error}
              selectedPath={selectedFile}
              onSelect={setSelectedFile}
              statusLabel={statusLabel}
              selectedLabel={compare.selected.label}
              currentLabel={compare.current.label}
              activeFile={activeFile}
              t={t}
            />
          )}
        </div>
      ) : (
        <Table
          rowKey="id"
          size="small"
          loading={loading || compareLoading}
          columns={columns}
          dataSource={items}
          pagination={{
            current: page,
            pageSize,
            total,
            hideOnSinglePage: true,
            onChange: (nextPage) => load(nextPage),
          }}
        />
      )}
    </OperateDrawer>
  );
};

const FieldChanges = ({
  fields,
  labelOf,
}: {
  fields: TemplateFieldDiff[];
  labelOf: (key: string) => string;
}) => (
  <div className="flex flex-col gap-2 text-sm">
    {fields.map((field) => (
      <div key={field.key} className="rounded border border-[var(--color-border-1)] px-3 py-2">
        <div className="mb-1 text-[var(--color-text-3)]">{labelOf(field.key)}</div>
        <div className="text-[var(--color-text-1)]">{String(field.selected ?? '')} → {String(field.current ?? '')}</div>
      </div>
    ))}
  </div>
);

const DiffBlock = ({
  title,
  selectedLabel,
  currentLabel,
  selected,
  current,
}: {
  title?: string;
  selectedLabel: string;
  currentLabel: string;
  selected: string;
  current: string;
}) => (
  <div>
    {title ? <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">{title}</div> : null}
    <div className="overflow-auto rounded border border-[var(--color-border-1)]">
      <ReactDiffViewer
        oldValue={selected || ''}
        newValue={current || ''}
        splitView
        leftTitle={selectedLabel}
        rightTitle={currentLabel}
      />
    </div>
  </div>
);

const ParamChanges = ({
  params,
  statusLabel,
  t,
}: {
  params: TemplateParamDiff[];
  statusLabel: (status: string) => string;
  t: (key: string) => string;
}) => {
  if (!params.length) return null;
  return (
    <div>
      <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">{t('job.paramDiff')}</div>
      <Table
        size="small"
        rowKey="name"
        pagination={false}
        dataSource={params}
        columns={[
          { title: t('job.parameterName'), dataIndex: 'name' },
          { title: t('job.status'), dataIndex: 'status', render: (status: string) => statusLabel(status) },
          {
            title: t('job.defaultVal'),
            render: (_value, record: TemplateParamDiff) => {
              const encrypted = record.current?.is_encrypted || record.selected?.is_encrypted;
              if (encrypted) {
                return record.default_changed ? t('job.encryptedDefaultChanged') : t('job.encryptedDefaultUnchanged');
              }
              return `${record.selected?.default || '--'} → ${record.current?.default || '--'}`;
            },
          },
        ]}
      />
    </div>
  );
};

const FileChanges = ({
  files,
  archiveError,
  selectedPath,
  onSelect,
  statusLabel,
  selectedLabel,
  currentLabel,
  activeFile,
  t,
}: {
  files: TemplateFileDiff[];
  archiveError: string;
  selectedPath: string;
  onSelect: (path: string) => void;
  statusLabel: (status: string) => string;
  selectedLabel: string;
  currentLabel: string;
  activeFile?: TemplateFileDiff;
  t: (key: string) => string;
}) => (
  <div className="flex flex-col gap-3">
    <div className="text-sm font-medium text-[var(--color-text-1)]">{t('job.fileDiff')}</div>
    {archiveError ? <Alert type="warning" showIcon message={t('job.archiveUnreadable')} /> : null}
    <Table
      size="small"
      rowKey="path"
      pagination={false}
      dataSource={files}
      columns={[
        {
          title: t('job.fileListTab'),
          dataIndex: 'path',
          render: (path: string) => (
            <a className="cursor-pointer text-[var(--color-primary)]" onClick={() => onSelect(path)}>
              {path}
            </a>
          ),
        },
        { title: t('job.status'), dataIndex: 'status', render: (status: string) => statusLabel(status) },
        {
          title: t('job.fileSize'),
          render: (_value, record: TemplateFileDiff) => `${formatByteSize(record.selected_size)} → ${formatByteSize(record.current_size)}`,
        },
        {
          title: t('job.operation'),
          width: 80,
          render: (_value, record: TemplateFileDiff) => (
            <a className="cursor-pointer text-[var(--color-primary)]" onClick={() => onSelect(record.path)}>
              {t('job.viewScript')}
            </a>
          ),
        },
      ]}
      rowClassName={(record) => record.path === selectedPath ? 'bg-[var(--color-fill-1)]' : ''}
    />
    <OperateDrawer
      title={activeFile?.path}
      subTitle={activeFile ? `${selectedLabel} / ${currentLabel}` : ''}
      width={960}
      zIndex={1300}
      open={Boolean(activeFile)}
      onClose={() => onSelect('')}
      destroyOnHidden
      styles={{ body: { overflow: 'auto' } }}
    >
      {activeFile ? (
        <div className="flex flex-col gap-4">
          <div className="text-sm text-[var(--color-text-2)]">
            {`${formatByteSize(activeFile.selected_size)} → ${formatByteSize(activeFile.current_size)}`}
          </div>
          {activeFile.binary || activeFile.too_large ? (
            <Alert type="info" showIcon message={t('job.compareSizeOnly')} />
          ) : activeFile.status === 'unchanged' ? (
            <Alert type="info" showIcon message={t('job.fileContentSame')} />
          ) : (
            <DiffBlock
              selectedLabel={selectedLabel}
              currentLabel={currentLabel}
              selected={activeFile.selected_text}
              current={activeFile.current_text}
            />
          )}
        </div>
      ) : null}
    </OperateDrawer>
  </div>
);

export default TemplateVersionDrawer;
