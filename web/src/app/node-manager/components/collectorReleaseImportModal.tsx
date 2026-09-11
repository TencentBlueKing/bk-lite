'use client';

import { useMemo, useState, type ReactNode } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Modal,
  Result,
  Tag,
  Upload,
  message
} from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import { useTranslation } from '@/utils/i18n';
import useNodeManagerApi from '@/app/node-manager/api';
import { HandledRequestError } from '@/utils/request';
import PermissionWrapper from '@/components/permission';

interface PackIssue {
  code: string;
  message: string;
  hint?: string;
  level?: string;
  details?: Record<string, unknown>;
}

interface ImportResult {
  token?: string;
  has_errors?: boolean;
  issues?: PackIssue[];
  requires_confirm?: string[];
  pack?: {
    collector?: string;
    version?: string;
    collect_type?: string;
    artifacts?: Array<{ os: string; arch: string; sha256?: string }>;
    hashes?: Record<string, string>;
    allowlist?: { flags?: string[]; form_fields?: string[] };
  };
  ok?: boolean;
  collector?: string;
  version?: string;
  artifacts?: Array<{ os: string; arch: string; action: string }>;
  message?: string;
}

interface PackPreviewItem {
  key: string;
  file: File;
  preview: ImportResult;
  confirms: string[];
  applied?: ImportResult;
  applyFailed?: boolean;
}

interface CollectorReleaseImportModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const PACK_VERSION_COL_WIDTH = 72;
const PACK_ARCH_COL_WIDTH = 184;
const PACK_STATUS_COL_WIDTH = 108;

const fileKey = (file: File) => `${file.name}-${file.size}-${file.lastModified}`;

const mergeZipFiles = (current: File[], incoming: File[]) => {
  const next = new Map(current.map((file) => [fileKey(file), file]));
  incoming.forEach((file) => {
    if (!/\.zip$/i.test(file.name)) {
      return;
    }
    next.set(fileKey(file), file);
  });
  return [...next.values()];
};

const isItemReady = (item: PackPreviewItem) => {
  const required = item.preview.requires_confirm || [];
  return (
    Boolean(item.preview.token) &&
    !item.preview.has_errors &&
    required.every((code) => item.confirms.includes(code))
  );
};

const CollectorReleaseImportModal = ({
  open,
  onClose,
  onSuccess
}: CollectorReleaseImportModalProps) => {
  const { t } = useTranslation();
  const { previewCollectorRelease, applyCollectorRelease } = useNodeManagerApi();
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<PackPreviewItem[] | null>(null);
  const [finished, setFinished] = useState(false);

  const readyItems = useMemo(
    () => (items || []).filter((item) => isItemReady(item) && !item.applied && !item.applyFailed),
    [items]
  );

  const reset = () => {
    setFiles([]);
    setItems(null);
    setFinished(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const mapHttpError = (error: unknown): ImportResult => {
    const handled = error instanceof HandledRequestError ? error : null;
    if (handled?.status === 413) {
      return {
        token: '',
        has_errors: true,
        issues: [
          {
            code: 'PACK_TOO_LARGE',
            message: t('node-manager.packetManage.packTooLarge'),
            hint: t('node-manager.packetManage.packTooLargeHint'),
            level: 'error'
          }
        ],
        requires_confirm: []
      };
    }
    if (handled?.status === 404) {
      return {
        token: '',
        has_errors: true,
        issues: [
          {
            code: 'PREVIEW_HTTP_404',
            message: t('node-manager.packetManage.endpointMissing'),
            hint: t('node-manager.packetManage.endpointMissingHint'),
            level: 'error'
          }
        ],
        requires_confirm: []
      };
    }
    const payload = handled?.payload as
      | { data?: ImportResult; message?: string }
      | undefined;
    if (payload?.data?.issues) {
      return payload.data;
    }
    return {
      token: '',
      has_errors: true,
      issues: [
        {
          code: handled?.code || 'IMPORT_REQUEST_FAILED',
          message:
            error instanceof Error ? error.message : t('common.operationFailed'),
          level: 'error'
        }
      ],
      requires_confirm: []
    };
  };

  const handlePreview = async () => {
    if (!files.length) {
      message.warning(t('node-manager.packetManage.selectZip'));
      return;
    }
    setLoading(true);
    try {
      const nextItems: PackPreviewItem[] = [];
      for (const file of files) {
        try {
          const preview = await previewCollectorRelease(file);
          nextItems.push({
            key: fileKey(file),
            file,
            preview,
            confirms: []
          });
        } catch (error) {
          nextItems.push({
            key: fileKey(file),
            file,
            preview: mapHttpError(error),
            confirms: []
          });
        }
      }
      setItems(nextItems);
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!items?.length || !readyItems.length) return;
    setLoading(true);
    let imported = 0;
    try {
      const nextItems = [...items];
      for (const ready of readyItems) {
        const index = nextItems.findIndex((item) => item.key === ready.key);
        if (index < 0) continue;
        try {
          const result = await applyCollectorRelease({
            token: nextItems[index].preview.token || '',
            confirms: nextItems[index].confirms
          });
          if (result?.ok) {
            nextItems[index] = { ...nextItems[index], applied: result };
            imported += 1;
          } else {
            nextItems[index] = {
              ...nextItems[index],
              preview: { ...nextItems[index].preview, ...result, has_errors: true },
              applyFailed: true
            };
          }
        } catch (error) {
          nextItems[index] = {
            ...nextItems[index],
            preview: {
              ...nextItems[index].preview,
              ...mapHttpError(error),
              has_errors: true
            },
            applyFailed: true
          };
        }
      }
      setItems(nextItems);
      setFinished(true);
      if (imported > 0) {
        onSuccess();
      }
    } finally {
      setLoading(false);
    }
  };

  const updateConfirms = (key: string, confirms: string[]) => {
    setItems((current) =>
      (current || []).map((item) =>
        item.key === key ? { ...item, confirms } : item
      )
    );
  };

  const renderIssueLines = (issueItems: PackIssue[]) => {
    if (issueItems.length === 1) {
      const item = issueItems[0];
      return item.hint ? (
        <div className="text-sm text-[var(--color-text-3)]">{item.hint}</div>
      ) : null;
    }
    return (
      <ul className="mb-0 list-disc pl-5">
        {issueItems.map((item) => (
          <li key={`${item.code}-${item.message}`} className="mb-1 last:mb-0">
            <div>{item.message}</div>
            {item.hint ? (
              <div className="mt-1 text-sm text-[var(--color-text-3)]">
                {item.hint}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    );
  };

  const formatInfoNotes = (issues: PackIssue[]) => {
    const notes: string[] = [];
    const unchangedArches: string[] = [];
    issues.forEach((issue) => {
      if (issue.level !== 'info') return;
      if (issue.code === 'BINARY_UNCHANGED') {
        const os = typeof issue.details?.os === 'string' ? issue.details.os : '';
        const arch = typeof issue.details?.arch === 'string' ? issue.details.arch : '';
        if (os && arch) {
          unchangedArches.push(`${os}/${arch}`);
          return;
        }
        if (
          Array.isArray(issue.details?.kept) ||
          /未包含|not included/i.test(issue.message)
        ) {
          return;
        }
        const archMatch = issue.message.match(/^(\S+\/\S+)/);
        if (archMatch) {
          unchangedArches.push(archMatch[1]);
          return;
        }
      }
      notes.push(issue.message);
    });
    if (unchangedArches.length) {
      notes.unshift(
        t('node-manager.packetManage.unchangedBinaries', '', {
          arches: unchangedArches.join(' · ')
        })
      );
    }
    return notes;
  };

  const renderPackColumns = (
    name: ReactNode,
    version: ReactNode,
    arch: ReactNode,
    status?: ReactNode
  ) => (
    <div className="flex items-start gap-3">
      <div className="min-w-0 flex-1">{name}</div>
      <div className="shrink-0" style={{ width: PACK_VERSION_COL_WIDTH }}>
        {version}
      </div>
      <div
        className="flex shrink-0 flex-wrap items-center gap-1"
        style={{ width: PACK_ARCH_COL_WIDTH }}
      >
        {arch}
      </div>
      {status !== undefined ? (
        <div className="shrink-0" style={{ width: PACK_STATUS_COL_WIDTH }}>
          {status}
        </div>
      ) : null}
    </div>
  );

  const renderPackRow = (
    collector?: string,
    version?: string,
    artifacts?: Array<{ os: string; arch: string }>,
    fileName?: string,
    extra?: ReactNode,
    status?: ReactNode
  ) => {
    if (!collector && !version && !fileName) return null;
    return (
      <div>
        {renderPackColumns(
          <>
            <h3 className="m-0 text-sm font-medium leading-normal text-[var(--color-text-1)]">
              {collector || fileName}
            </h3>
            {fileName && collector ? (
              <div className="mt-0.5 truncate text-sm leading-normal text-[var(--color-text-3)]">
                {fileName}
              </div>
            ) : null}
          </>,
          <div className="pt-0.5 text-sm font-medium tabular-nums leading-normal text-[var(--color-text-1)]">
            {version || '—'}
          </div>,
          (artifacts || []).map((item) => (
            <Tag key={`${item.os}-${item.arch}`} className="m-0">
              {item.os}/{item.arch}
            </Tag>
          )),
          status
        )}
        {extra}
      </div>
    );
  };

  const renderPackListHeader = (showStatus = false) => (
    <div className="px-4 text-sm leading-normal text-[var(--color-text-3)]">
      {renderPackColumns(
        t('node-manager.packetManage.packColumn'),
        t('node-manager.packetManage.version'),
        t('node-manager.packetManage.archColumn'),
        showStatus ? t('node-manager.packetManage.statusColumn') : undefined
      )}
    </div>
  );

  const renderPackList = (
    rows: ReactNode,
    maxHeightClassName: string,
    showStatus = false
  ) => (
    <div className={`flex w-full flex-col gap-3 ${maxHeightClassName} overflow-y-auto text-left`}>
      {renderPackListHeader(showStatus)}
      <ul className="m-0 flex list-none flex-col gap-3 p-0">{rows}</ul>
    </div>
  );

  const renderItemIssues = (item: PackPreviewItem, readonly: boolean) => {
    const issues = item.preview.issues || [];
    const errors = issues.filter((issue) => issue.level === 'error');
    const warnings = issues.filter((issue) => issue.level === 'warning');
    const notes = formatInfoNotes(issues);
    if (
      !notes.length &&
      !errors.length &&
      !(warnings.length && !item.preview.has_errors)
    ) {
      return null;
    }
    return (
      <div className="mt-2 flex flex-col gap-2">
        {notes.length > 0 ? (
          <Alert
            type="info"
            showIcon
            className="!rounded-xl"
            message={
              notes.length === 1 ? (
                notes[0]
              ) : (
                <ul className="mb-0 list-disc pl-4">
                  {notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              )
            }
          />
        ) : null}
        {errors.length > 0 ? (
          <Alert
            type="error"
            showIcon
            className="!rounded-xl"
            message={
              errors.length === 1
                ? errors[0].message
                : t('node-manager.packetManage.errorGroup')
            }
            description={renderIssueLines(errors) || undefined}
          />
        ) : null}
        {warnings.length > 0 && !item.preview.has_errors ? (
          <div>
            <div className="mb-1 text-sm text-[var(--color-text-1)]">
              {t('node-manager.packetManage.confirmRequired')}
            </div>
            <Checkbox.Group
              className="flex flex-col gap-2"
              disabled={readonly}
              value={item.confirms}
              onChange={(values) => updateConfirms(item.key, values as string[])}
              options={warnings.map((issue) => ({
                label: (
                  <span className="whitespace-normal text-sm leading-normal">
                    {issue.message}
                    {issue.hint ? (
                      <span className="mt-1 block text-sm text-[var(--color-text-3)]">
                        {issue.hint}
                      </span>
                    ) : null}
                  </span>
                ),
                value: issue.code
              }))}
            />
          </div>
        ) : null}
      </div>
    );
  };

  const renderFinishedSummary = () => {
    const imported = (items || []).filter((item) => item.applied?.ok);
    const failed = (items || []).filter((item) => item.applyFailed);
    const skipped = (items || []).filter(
      (item) => !item.applied?.ok && !item.applyFailed
    );
    const title =
      imported.length && !failed.length && !skipped.length
        ? t('node-manager.packetManage.importSummarySuccess', '', {
          count: imported.length
        })
        : imported.length
          ? t('node-manager.packetManage.importSummaryPartial', '', {
            ok: imported.length,
            failed: failed.length,
            skipped: skipped.length
          })
          : t('node-manager.packetManage.importSummaryFailed');
    return (
      <Result
        status={imported.length ? (failed.length ? 'warning' : 'success') : 'error'}
        title={title}
        subTitle={t('node-manager.packetManage.successNeedSave')}
        extra={renderPackList(
          (items || []).map((item) => {
            const status = item.applied?.ok
              ? t('node-manager.packetManage.statusImported')
              : item.applyFailed
                ? t('node-manager.packetManage.statusFailed')
                : t('node-manager.packetManage.statusSkipped');
            return (
                <li
                  key={item.key}
                  className="rounded-xl border border-[var(--color-border-1)] px-4 py-3"
                >
                  {renderPackRow(
                    item.applied?.collector || item.preview.pack?.collector,
                    item.applied?.version || item.preview.pack?.version,
                    item.applied?.artifacts || item.preview.pack?.artifacts,
                    item.file.name,
                    item.applyFailed ? renderItemIssues(item, true) : null,
                    <Tag
                      className="m-0"
                      color={
                        item.applied?.ok
                          ? 'success'
                          : item.applyFailed
                            ? 'error'
                            : 'default'
                      }
                    >
                      {status}
                    </Tag>
                  )}
                </li>
            );
          }),
          'max-h-[360px]',
          true
        )}
      />
    );
  };

  const uploadFileList: UploadFile[] = files.map((file) => ({
    uid: fileKey(file),
    name: file.name,
    status: 'done',
    originFileObj: file as UploadFile['originFileObj']
  }));

  return (
    <Modal
      title={t('node-manager.packetManage.importPackTitle')}
      open={open}
      onCancel={handleClose}
      width={760}
      destroyOnHidden
      footer={
        finished ? (
          <Button type="primary" onClick={handleClose}>
            {t('common.close')}
          </Button>
        ) : (
          <>
            <Button onClick={handleClose}>{t('common.cancel')}</Button>
            {items ? (
              <Button onClick={reset}>{t('node-manager.packetManage.reselect')}</Button>
            ) : null}
            {!items ? (
              <Button type="primary" loading={loading} onClick={handlePreview}>
                {t('node-manager.packetManage.preview')}
              </Button>
            ) : (
              <PermissionWrapper requiredPermissions={['AddPacket']}>
                <Button
                  type="primary"
                  loading={loading}
                  disabled={!readyItems.length}
                  onClick={handleApply}
                >
                  {readyItems.length > 1
                    ? t('node-manager.packetManage.applySelected', '', {
                      count: readyItems.length
                    })
                    : t('node-manager.packetManage.apply')}
                </Button>
              </PermissionWrapper>
            )}
          </>
        )
      }
    >
      {finished ? (
        renderFinishedSummary()
      ) : (
        <div className="flex flex-col gap-3">
          {!items ? (
            <>
              <p className="mb-0 text-sm text-[var(--color-text-3)]">
                {t('node-manager.packetManage.importPackHint')}
              </p>
              <Upload.Dragger
                multiple
                accept=".zip"
                beforeUpload={(file) => {
                  if (!/\.zip$/i.test(file.name)) {
                    message.warning(t('node-manager.packetManage.selectZip'));
                    return false;
                  }
                  setFiles((current) => mergeZipFiles(current, [file]));
                  return false;
                }}
                onRemove={(uploadFile) => {
                  setFiles((current) =>
                    current.filter((file) => fileKey(file) !== uploadFile.uid)
                  );
                }}
                fileList={uploadFileList}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p>{t('node-manager.packetManage.selectZip')}</p>
              </Upload.Dragger>
            </>
          ) : (
            renderPackList(
              items.map((item) => (
                <li
                  key={item.key}
                  className="rounded-xl border border-[var(--color-border-1)] px-4 py-3"
                >
                  {renderPackRow(
                    item.preview.pack?.collector,
                    item.preview.pack?.version,
                    item.preview.pack?.artifacts,
                    item.file.name,
                    renderItemIssues(item, false)
                  )}
                </li>
              )),
              'max-h-[480px]'
            )
          )}
        </div>
      )}
    </Modal>
  );
};

export default CollectorReleaseImportModal;
