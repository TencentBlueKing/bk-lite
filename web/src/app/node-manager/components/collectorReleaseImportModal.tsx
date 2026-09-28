'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Modal,
  Result,
  Tag,
  Tooltip,
  Upload,
  message
} from 'antd';
import { InboxOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import { useTranslation } from '@/utils/i18n';
import useNodeManagerApi from '@/app/node-manager/api';
import { HandledRequestError } from '@/utils/request';
import PermissionWrapper from '@/components/permission';
import { useScreenAwareRouter } from '@/console-layout';
import { MODULE_OBJECT_QUERY_PARAM } from '@/app/monitor/utils/monitorObjectQuery';
import { buildCollectNeedUpdateAssetUrl } from '@/app/monitor/utils/collectNeedUpdate';
import {
  IMPORT_STALE_LIST_PATH,
  IMPORT_STALE_NAMED_HINT_LIMIT,
  hasCollectorProgramChange,
  listStaleAssetTargets,
  resolveImportStaleAction
} from '@/app/node-manager/utils/importStaleAction';

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
  monitor_object_id?: number | string | null;
  plugin_id?: number | string | null;
  stale_instance_count?: number;
  first_fingerprint?: boolean;
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

const INTEGRATION_LIST_PATH = IMPORT_STALE_LIST_PATH;
const NODE_PATH = '/node-manager/cloudregion/node';

export const buildCollectorReleaseIntegrationListUrl = (
  items: Array<{ applied?: Pick<ImportResult, 'ok' | 'monitor_object_id'> | null }>
): string => {
  const objectId = items
    .map((item) => item.applied)
    .find((applied) => {
      if (!applied?.ok || applied.monitor_object_id == null) {
        return false;
      }
      return String(applied.monitor_object_id).trim() !== '';
    })?.monitor_object_id;
  if (objectId == null || String(objectId).trim() === '') {
    return INTEGRATION_LIST_PATH;
  }
  return `${INTEGRATION_LIST_PATH}?${MODULE_OBJECT_QUERY_PARAM}=${encodeURIComponent(String(objectId))}`;
};

export const buildCollectorReleaseNodeUrl = (
  items: Array<{
    applied?: Pick<
      ImportResult,
      'ok' | 'collector' | 'monitor_object_id' | 'plugin_id'
    > | null;
  }>
): string => {
  const params = new URLSearchParams();
  const collectors: string[] = [];
  const seen = new Set<string>();
  let objectId: string | number | null = null;
  let pluginId: string | number | null = null;
  for (const item of items || []) {
    const applied = item.applied;
    if (!applied?.ok) continue;
    const collector = String(applied.collector || '').trim();
    if (collector && !seen.has(collector.toLowerCase())) {
      seen.add(collector.toLowerCase());
      collectors.push(collector);
    }
    if (
      objectId == null &&
      applied.monitor_object_id != null &&
      String(applied.monitor_object_id).trim() !== ''
    ) {
      objectId = applied.monitor_object_id;
    }
    if (
      pluginId == null &&
      applied.plugin_id != null &&
      String(applied.plugin_id).trim() !== ''
    ) {
      pluginId = applied.plugin_id;
    }
  }
  if (collectors.length) {
    params.set('collector', collectors.join(','));
  }
  if (objectId != null) {
    params.set(MODULE_OBJECT_QUERY_PARAM, String(objectId));
  }
  if (pluginId != null) {
    params.set('plugin_id', String(pluginId));
  }
  const query = params.toString();
  return query ? `${NODE_PATH}?${query}` : NODE_PATH;
};

export const buildCollectorReleaseStaleAssetUrl = (
  items: Array<{ applied?: Pick<ImportResult, 'ok' | 'monitor_object_id' | 'plugin_id' | 'stale_instance_count'> | null }>
): string => {
  const applied = items
    .map((item) => item.applied)
    .find((item) => item?.ok && (item.stale_instance_count || 0) > 0);
  return buildCollectNeedUpdateAssetUrl({
    monitorObjectId: applied?.monitor_object_id,
    pluginId: applied?.plugin_id,
    needUpdate: true
  });
};

const sumStaleInstanceCount = (
  items: Array<{ applied?: Pick<ImportResult, 'ok' | 'stale_instance_count'> | null }>
) =>
  (items || []).reduce((total, item) => {
    if (!item.applied?.ok) return total;
    return total + (Number(item.applied.stale_instance_count) || 0);
  }, 0);

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

const warningCodesForItem = (item: PackPreviewItem): string[] => {
  if (item.preview.has_errors) return [];
  const fromRequires = item.preview.requires_confirm || [];
  if (fromRequires.length) return fromRequires;
  return (item.preview.issues || [])
    .filter((issue) => issue.level === 'warning')
    .map((issue) => issue.code)
    .filter(Boolean);
};

const isItemFullyConfirmed = (item: PackPreviewItem) => {
  const required = warningCodesForItem(item);
  return required.length > 0 && required.every((code) => item.confirms.includes(code));
};

const PLUGIN_REPLACE_CODES = new Set(['PLUGIN_OVERWRITE', 'PLUGIN_DOWNGRADE']);

const isPluginReplaceIssue = (issue: PackIssue) =>
  issue.level === 'warning' && PLUGIN_REPLACE_CODES.has(issue.code);

const itemHasPluginReplaceWarning = (item: PackPreviewItem) =>
  (item.preview.issues || []).some(isPluginReplaceIssue);

const CollectorReleaseImportModal = ({
  open,
  onClose,
  onSuccess
}: CollectorReleaseImportModalProps) => {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const {
    previewCollectorRelease,
    applyCollectorRelease,
    discardCollectorRelease
  } = useNodeManagerApi();
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<PackPreviewItem[] | null>(null);
  const [finished, setFinished] = useState(false);
  const [previewProgress, setPreviewProgress] = useState<{
    current: number;
    total: number;
  } | null>(null);
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewingRef = useRef(false);
  const previewSeqRef = useRef(0);

  useEffect(() => {
    return () => {
      if (previewTimerRef.current) {
        clearTimeout(previewTimerRef.current);
      }
    };
  }, []);

  const readyItems = useMemo(
    () => (items || []).filter((item) => isItemReady(item) && !item.applied && !item.applyFailed),
    [items]
  );

  const confirmableItems = useMemo(
    () =>
      (items || []).filter(
        (item) =>
          !item.applied &&
          !item.applyFailed &&
          !item.preview.has_errors &&
          warningCodesForItem(item).length > 0
      ),
    [items]
  );

  const allWarningsConfirmed = useMemo(
    () =>
      confirmableItems.length > 0 &&
      confirmableItems.every((item) => isItemFullyConfirmed(item)),
    [confirmableItems]
  );

  const someWarningsConfirmed = useMemo(
    () =>
      confirmableItems.some((item) => isItemFullyConfirmed(item)) &&
      !allWarningsConfirmed,
    [confirmableItems, allWarningsConfirmed]
  );

  const staleTargets = useMemo(
    () => listStaleAssetTargets(items || []),
    [items]
  );
  const staleAction = useMemo(
    () => resolveImportStaleAction(staleTargets),
    [staleTargets]
  );
  const staleCount = useMemo(
    () => sumStaleInstanceCount(items || []),
    [items]
  );
  const programChanged = useMemo(
    () => hasCollectorProgramChange(items || []),
    [items]
  );

  // 预览会在服务端暂存整包，放弃时主动释放，不必等服务端的回收窗口。
  const discardPendingStaging = (pending: PackPreviewItem[] | null) => {
    (pending || []).forEach((item) => {
      const token = item.preview.token;
      if (!token || item.applied?.ok) return;
      void Promise.resolve(discardCollectorRelease(token)).catch(
        () => undefined
      );
    });
  };

  const reset = () => {
    previewSeqRef.current += 1;
    previewingRef.current = false;
    if (previewTimerRef.current) {
      clearTimeout(previewTimerRef.current);
      previewTimerRef.current = null;
    }
    discardPendingStaging(items);
    setFiles([]);
    setItems(null);
    setFinished(false);
    setPreviewProgress(null);
    setLoading(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const goToNodeProgram = () => {
    handleClose();
    router.push(buildCollectorReleaseNodeUrl(items || []));
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

  const runPreview = async (targetFiles: File[]) => {
    if (!targetFiles.length) {
      message.warning(t('node-manager.packetManage.selectZip'));
      return;
    }
    if (previewingRef.current) {
      return;
    }
    previewingRef.current = true;
    const seq = previewSeqRef.current + 1;
    previewSeqRef.current = seq;
    setLoading(true);
    setPreviewProgress({ current: 1, total: targetFiles.length });
    try {
      const nextItems: PackPreviewItem[] = [];
      for (let index = 0; index < targetFiles.length; index += 1) {
        if (seq !== previewSeqRef.current) {
          return;
        }
        setPreviewProgress({ current: index + 1, total: targetFiles.length });
        const file = targetFiles[index];
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
      if (seq !== previewSeqRef.current) {
        return;
      }
      setItems(nextItems);
    } finally {
      if (seq === previewSeqRef.current) {
        previewingRef.current = false;
        setLoading(false);
        setPreviewProgress(null);
      }
    }
  };

  const schedulePreview = (targetFiles: File[]) => {
    if (previewingRef.current) {
      return;
    }
    if (previewTimerRef.current) {
      clearTimeout(previewTimerRef.current);
    }
    previewTimerRef.current = setTimeout(() => {
      void runPreview(targetFiles);
    }, 50);
  };

  const handlePreview = () => {
    if (previewingRef.current) {
      return;
    }
    if (!files.length) {
      return;
    }
    if (previewTimerRef.current) {
      clearTimeout(previewTimerRef.current);
      previewTimerRef.current = null;
    }
    void runPreview(files);
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

  const toggleConfirmAllWarnings = (checked: boolean) => {
    setItems((current) =>
      (current || []).map((item) => {
        if (item.applied || item.applyFailed || item.preview.has_errors) {
          return item;
        }
        const required = warningCodesForItem(item);
        if (!required.length) return item;
        return { ...item, confirms: checked ? required : [] };
      })
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
    artifacts?: Array<{ os: string; arch: string; sha256?: string }>,
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
          (artifacts || []).map((item) => {
            const tag = (
              <Tag key={`${item.os}-${item.arch}`} className="m-0">
                {item.os}/{item.arch}
              </Tag>
            );
            // 二进制指纹只在悬停时给出，便于与发布说明核对，又不占版面。
            return item.sha256 ? (
              <Tooltip
                key={`${item.os}-${item.arch}`}
                title={t('node-manager.packetManage.artifactFingerprint', '', {
                  sha256: item.sha256
                })}
              >
                {tag}
              </Tooltip>
            ) : (
              tag
            );
          }),
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

  const formatWarningConfirmLabel = (issue: PackIssue) => {
    const current = String(issue.details?.current || '').trim();
    const incoming = String(issue.details?.incoming || '').trim();
    const version = String(issue.details?.version || '').trim();
    if (issue.code === 'PLUGIN_DOWNGRADE' && current && incoming) {
      return t('node-manager.packetManage.replacePackVersionDowngrade', '', {
        current,
        incoming
      });
    }
    if (issue.code === 'PLUGIN_OVERWRITE' && current && incoming) {
      return t('node-manager.packetManage.replacePackVersion', '', {
        current,
        incoming
      });
    }
    if (issue.code === 'PLUGIN_OVERWRITE' && version) {
      return t('node-manager.packetManage.replacePackSameVersion', '', {
        version
      });
    }
    return issue.message;
  };

  const renderVersionMark = (version: string) => (
    <span className="font-semibold tabular-nums text-[var(--color-text-1)]">
      {version}
    </span>
  );

  const renderPluginReplaceLabel = (issue: PackIssue) => {
    const current = String(issue.details?.current || '').trim();
    const incoming = String(issue.details?.incoming || '').trim();
    const version = String(issue.details?.version || '').trim();
    const body =
      current && incoming ? (
        <>
          <span>{t('node-manager.packetManage.replacePackFrom')}</span>
          {renderVersionMark(current)}
          <span aria-hidden="true">→</span>
          <span>{t('node-manager.packetManage.replacePackTo')}</span>
          {renderVersionMark(incoming)}
          {issue.code === 'PLUGIN_DOWNGRADE' ? (
            <span>（{t('node-manager.packetManage.replacePackDowngradeMark')}）</span>
          ) : null}
        </>
      ) : version ? (
        <>
          <span>
            {t('node-manager.packetManage.replacePackSameVersionPrefix')}
          </span>
          {renderVersionMark(version)}
        </>
      ) : (
        formatWarningConfirmLabel(issue)
      );

    return (
      <span className="inline-flex max-w-full flex-wrap items-center gap-1 rounded-md border border-[var(--ant-color-warning-border)] bg-[var(--ant-color-warning-bg)] px-2 py-0.5 text-sm leading-5 text-[var(--color-text-2)]">
        {body}
      </span>
    );
  };

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
          <Checkbox.Group
            className="flex w-full flex-col gap-1"
            disabled={readonly}
            value={item.confirms}
            onChange={(values) => updateConfirms(item.key, values as string[])}
            options={warnings.map((issue) => ({
              label: (
                <span className="inline-flex max-w-full items-center whitespace-normal">
                  {isPluginReplaceIssue(issue) ? (
                    renderPluginReplaceLabel(issue)
                  ) : (
                    <span className="text-sm leading-relaxed text-[var(--color-text-1)]">
                      {formatWarningConfirmLabel(issue)}
                    </span>
                  )}
                </span>
              ),
              value: issue.code
            }))}
          />
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
    const staleHint =
      staleCount > 0 ? (
        <div className="space-y-1 text-sm leading-relaxed text-[var(--color-text-2)]">
          <div>
            {t('node-manager.packetManage.successStaleCollect', '', {
              count: staleCount
            })}
          </div>
          {staleAction.many ? (
            <div className="text-[var(--color-text-3)]">
              {staleTargets.length <= IMPORT_STALE_NAMED_HINT_LIMIT
                ? t('node-manager.packetManage.successStaleManyNamed', '', {
                  names: staleTargets.map((target) => target.label).join('、')
                })
                : t('node-manager.packetManage.successStaleManyCount', '', {
                  count: staleTargets.length
                })}
            </div>
          ) : null}
        </div>
      ) : null;
    const programHint = programChanged ? (
      <div className="text-sm leading-relaxed text-[var(--color-text-3)]">
        {staleCount > 0
          ? t('node-manager.packetManage.successProgramChanged')
          : t('node-manager.packetManage.successNeedSaveProgram')}{' '}
        <Button
          type="link"
          className="h-auto px-0 align-baseline"
          onClick={goToNodeProgram}
        >
          {t('node-manager.packetManage.goInstallCollectorProgram')}
        </Button>
      </div>
    ) : null;
    return (
      <Result
        status={imported.length ? (failed.length ? 'warning' : 'success') : 'error'}
        title={title}
        subTitle={
          <div className="space-y-2">
            {staleHint}
            {staleCount > 0 ? null : (
              <div className="text-sm text-[var(--color-text-3)]">
                {t('node-manager.packetManage.successNeedSave')}
              </div>
            )}
            {programHint}
          </div>
        }
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
          <div className="flex w-full items-center justify-between gap-2 [&_button]:!mr-0">
            <Button onClick={handleClose}>{t('common.close')}</Button>
            {(items || []).some((item) => item.applied?.ok) ? (
              staleCount > 0 ? (
                <Button
                  type="primary"
                  onClick={() => {
                    handleClose();
                    router.push(staleAction.href);
                  }}
                >
                  {t(`node-manager.packetManage.${staleAction.buttonKey}`)}
                </Button>
              ) : (
                <Button
                  type="primary"
                  onClick={() => {
                    handleClose();
                    router.push(
                      buildCollectorReleaseIntegrationListUrl(items || [])
                    );
                  }}
                >
                  {t('node-manager.packetManage.goToIntegration')}
                </Button>
              )
            ) : null}
          </div>
        ) : (
          // 统一 flex 底栏：避免 PermissionWrapper 的 span 打断 .ant-btn+.ant-btn
          // 间距，并抵消 node-manager 全局 footer button:nth-child(2) 的 margin。
          <div className="flex w-full items-center justify-end gap-2 [&_button]:!mr-0">
            <Button onClick={handleClose}>{t('common.cancel')}</Button>
            {items ? (
              <Button onClick={reset}>
                {t('node-manager.packetManage.reselect')}
              </Button>
            ) : null}
            {!items ? (
              <Button type="primary" loading={loading} onClick={handlePreview}>
                {t('node-manager.packetManage.preview')}
              </Button>
            ) : (
              <PermissionWrapper
                className="inline-flex"
                requiredPermissions={['AddPacket']}
              >
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
          </div>
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
                disabled={loading}
                beforeUpload={(file) => {
                  if (!/\.zip$/i.test(file.name)) {
                    message.warning(t('node-manager.packetManage.selectZip'));
                    return false;
                  }
                  setFiles((current) => {
                    const next = mergeZipFiles(current, [file]);
                    schedulePreview(next);
                    return next;
                  });
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
              {previewProgress ? (
                <p className="mb-0 text-sm text-[var(--color-text-3)]">
                  {previewProgress.total > 1
                    ? t('node-manager.packetManage.previewingProgress', '', {
                      current: previewProgress.current,
                      total: previewProgress.total
                    })
                    : t('node-manager.packetManage.previewing')}
                </p>
              ) : null}
            </>
          ) : (
            <div className="flex flex-col gap-3">
              {confirmableItems.length > 0 ? (
                <Alert
                  type="warning"
                  showIcon
                  className="!rounded-xl"
                  message={
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <Checkbox
                        checked={allWarningsConfirmed}
                        indeterminate={someWarningsConfirmed}
                        disabled={loading}
                        onChange={(event) =>
                          toggleConfirmAllWarnings(event.target.checked)
                        }
                      >
                        <span className="font-medium">
                          {t('node-manager.packetManage.confirmAllWarnings', '', {
                            count: confirmableItems.length
                          })}
                        </span>
                      </Checkbox>
                      <span className="shrink-0 text-sm font-normal text-[var(--color-text-3)]">
                        {t('node-manager.packetManage.confirmAllWarningsHint')}
                      </span>
                    </div>
                  }
                  description={
                    confirmableItems.some(itemHasPluginReplaceWarning) ? (
                      <div className="space-y-1 text-sm leading-relaxed">
                        <div>{t('node-manager.packetManage.confirmSharedPolicy')}</div>
                        <div className="text-[var(--color-text-3)]">
                          {t('node-manager.packetManage.confirmSharedHint')}
                        </div>
                      </div>
                    ) : undefined
                  }
                />
              ) : null}
              {renderPackList(
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
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};

export default CollectorReleaseImportModal;
