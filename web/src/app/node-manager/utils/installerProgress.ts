import {
  ControllerInstallProgressRow,
  InstallerFailure,
  InstallerFailureContext,
  InstallerEventSummary,
  InstallerProgressMetric,
  InstallerProgressSummary,
  InstallerStepCode,
  InstallerStepLabelMap,
  LogStep,
  OperationTaskResult
} from '../types/controller';

type TranslationFunction = (key: string) => string;

type InstallerFailureType = NonNullable<InstallerFailure['type']>;

const VALID_INSTALLER_STATUSES = new Set([
  'success',
  'error',
  'timeout',
  'running',
  'waiting',
  'installing',
  'installed'
]);

const clampNumber = (value: number, min: number, max: number) => {
  return Math.min(max, Math.max(min, value));
};

const normalizeNumber = (value?: number) => {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const normalizeText = (value?: string | null) => {
  if (typeof value !== 'string') {
    return null;
  }

  const normalized = value.trim();
  return normalized || null;
};

const normalizeFailureContext = (context?: InstallerFailureContext | null) => {
  if (!context) {
    return undefined;
  }

  const normalizedContext: InstallerFailureContext = {};
  const bucket = normalizeText(context.bucket);
  const fileKey = normalizeText(context.file_key);
  const packageName = normalizeText(context.package_name);
  const cpuArchitecture = normalizeText(context.cpu_architecture);
  const installDir = normalizeText(context.install_dir);
  const targetPath = normalizeText(context.target_path);
  const exitCode = normalizeNumber(context.exit_code);

  if (bucket) normalizedContext.bucket = bucket;
  if (fileKey) normalizedContext.file_key = fileKey;
  if (packageName) normalizedContext.package_name = packageName;
  if (cpuArchitecture) normalizedContext.cpu_architecture = cpuArchitecture;
  if (installDir) normalizedContext.install_dir = installDir;
  if (targetPath) normalizedContext.target_path = targetPath;
  if (exitCode !== null) normalizedContext.exit_code = Math.round(exitCode);

  return Object.keys(normalizedContext).length ? normalizedContext : undefined;
};

const normalizeFailure = (failure?: InstallerFailure | null) => {
  if (!failure) {
    return undefined;
  }

  const normalizedFailure: InstallerFailure = {};
  const message = normalizeText(failure.message);
  const type = normalizeText(failure.type);
  const summary = normalizeText(failure.summary);
  const rawError = normalizeText(failure.raw_error);
  const code = normalizeNumber(failure.code);
  const context = normalizeFailureContext(failure.context);

  if (message) normalizedFailure.message = message;
  if (type) normalizedFailure.type = type;
  if (summary) normalizedFailure.summary = summary;
  if (rawError) normalizedFailure.raw_error = rawError;
  if (code !== null) normalizedFailure.code = Math.round(code);
  if (typeof failure.retriable === 'boolean') normalizedFailure.retriable = failure.retriable;
  if (context) normalizedFailure.context = context;

  return Object.keys(normalizedFailure).length ? normalizedFailure : undefined;
};

const normalizeProgress = (progress?: InstallerProgressMetric) => {
  if (!progress) {
    return null;
  }

  const percent = normalizeNumber(progress.percent);
  const current = normalizeNumber(progress.current);
  const total = normalizeNumber(progress.total);

  return {
    percent: percent === null ? null : clampNumber(Math.round(percent), 0, 100),
    current: current === null ? null : Math.max(current, 0),
    total: total === null ? null : Math.max(total, 0),
    unit: normalizeText(progress.unit)
  };
};

const normalizeStringList = (values?: string[] | null) => {
  if (!Array.isArray(values)) {
    return [];
  }

  return values
    .map((value) => normalizeText(value))
    .filter((value): value is string => Boolean(value));
};

export const normalizeInstallerStatus = (status?: string | null) => {
  if (!status) {
    return 'waiting';
  }

  return VALID_INSTALLER_STATUSES.has(status) ? status : 'running';
};

export const normalizeInstallerLogs = (steps?: LogStep[] | null): LogStep[] => {
  if (!Array.isArray(steps)) {
    return [];
  }

  return steps.map((step, index) => ({
    action: normalizeText(step.action) || `Step ${index + 1}`,
    status: normalizeInstallerStatus(step.status),
    message:
      normalizeText(step.message) ||
      normalizeText(step.details?.installer_message) ||
      '--',
    timestamp: normalizeText(step.timestamp) || '',
    details: step.details
      ? {
        ...step.details,
        raw_step: step.details.raw_step,
        step_index:
          normalizeNumber(step.details.step_index) === null
            ? undefined
            : Math.max(Math.round(step.details.step_index as number), 0),
        step_total:
          normalizeNumber(step.details.step_total) === null
            ? undefined
            : Math.max(Math.round(step.details.step_total as number), 0),
        progress: normalizeProgress(step.details.progress) || undefined,
        error: normalizeText(step.details.error) || undefined,
        installer_message:
          normalizeText(step.details.installer_message) || undefined,
        timestamp: normalizeText(step.details.timestamp) || undefined,
        failure: normalizeFailure(step.details.failure)
      }
      : undefined
  }));
};

export const normalizeInstallerSummary = (
  summary?: InstallerEventSummary | null
): InstallerEventSummary | undefined => {
  if (!summary) {
    return undefined;
  }

  const normalizedSummary: InstallerEventSummary = {
    state: normalizeText(summary.state) || undefined,
    expected_steps: normalizeStringList(summary.expected_steps) as InstallerStepCode[],
    expected_count:
      normalizeNumber(summary.expected_count) === null
        ? undefined
        : Math.max(Math.round(summary.expected_count as number), 0),
    observed_count:
      normalizeNumber(summary.observed_count) === null
        ? undefined
        : Math.max(Math.round(summary.observed_count as number), 0),
    completed_steps: normalizeStringList(summary.completed_steps) as InstallerStepCode[],
    completed_count:
      normalizeNumber(summary.completed_count) === null
        ? undefined
        : Math.max(Math.round(summary.completed_count as number), 0),
    missing_steps: normalizeStringList(summary.missing_steps) as InstallerStepCode[],
    duplicate_count:
      normalizeNumber(summary.duplicate_count) === null
        ? undefined
        : Math.max(Math.round(summary.duplicate_count as number), 0),
    last_step: (normalizeText(summary.last_step || undefined) as InstallerStepCode) || null,
    last_status: normalizeText(summary.last_status || undefined)
      ? normalizeInstallerStatus(summary.last_status)
      : null,
    anomalies: normalizeStringList(summary.anomalies),
    steps: normalizeInstallerLogs(summary.steps)
  };

  return normalizedSummary;
};

export const normalizeInstallerResult = (
  result?: OperationTaskResult | null
): OperationTaskResult | null => {
  if (!result) {
    return null;
  }

  let installerProgress: InstallerProgressSummary | undefined;

  if (result.installer_progress) {
    installerProgress = {
      ...result.installer_progress,
      current_status: normalizeInstallerStatus(
        result.installer_progress.current_status
      ),
      current_message:
        normalizeText(result.installer_progress.current_message) || undefined,
      progress: normalizeProgress(result.installer_progress.progress) || undefined,
      step_index:
        normalizeNumber(result.installer_progress.step_index) === null
          ? undefined
          : Math.max(Math.round(result.installer_progress.step_index as number), 0),
      step_total:
        normalizeNumber(result.installer_progress.step_total) === null
          ? undefined
          : Math.max(Math.round(result.installer_progress.step_total as number), 0)
    };
  }

  return {
    steps: normalizeInstallerLogs(result.steps),
    installer_progress: installerProgress,
    installer_summary: normalizeInstallerSummary(result.installer_summary),
    failure: normalizeFailure(result.failure)
  };
};

export const normalizeControllerInstallResult = normalizeInstallerResult;

export const normalizeControllerInstallRow = (
  row: ControllerInstallProgressRow
): ControllerInstallProgressRow => {
  return {
    ...row,
    status: normalizeInstallerStatus(row.status),
    result: normalizeInstallerResult(row.result)
  };
};

export const normalizeControllerInstallRows = (
  rows?: ControllerInstallProgressRow[] | null
): ControllerInstallProgressRow[] => {
  if (!Array.isArray(rows)) {
    return [];
  }

  return rows.map(normalizeControllerInstallRow);
};

export const INSTALLER_STEP_LABEL_KEYS: InstallerStepLabelMap = {
  credential_check: 'node-manager.cloudregion.node.stepCredentialCheck',
  run: 'node-manager.cloudregion.node.stepRunInstaller',
  connectivity_check: 'node-manager.cloudregion.node.stepWaitForNodeConnection',
  stop_run: 'node-manager.cloudregion.node.stepStopControllerService',
  delete_dir: 'node-manager.cloudregion.node.stepRemoveInstallationDirectory',
  delete_node: 'node-manager.cloudregion.node.stepRemoveNodeRecord',
  unzip: 'node-manager.cloudregion.node.stepExtractCollectorPackage',
  set_executable: 'node-manager.cloudregion.node.stepSetExecutablePermissions',
  prepare: 'node-manager.cloudregion.node.stepPreparePackage',
  dispatch_command: 'node-manager.cloudregion.node.stepSubmitCollectorAction',
  consume_ack: 'node-manager.cloudregion.node.stepWaitForSidecarAck',
  execute_command: 'node-manager.cloudregion.node.stepExecuteCollectorAction',
  callback_or_timeout: 'node-manager.cloudregion.node.stepAwaitCollectorResult',
  fetch_session: 'node-manager.cloudregion.node.installerStepFetchSession',
  prepare_dirs: 'node-manager.cloudregion.node.installerStepPrepareDirs',
  prepare_directories:
    'node-manager.cloudregion.node.installerStepPrepareDirs',
  download: 'node-manager.cloudregion.node.installerStepDownload',
  download_package: 'node-manager.cloudregion.node.installerStepDownload',
  extract: 'node-manager.cloudregion.node.installerStepExtract',
  extract_package: 'node-manager.cloudregion.node.installerStepExtract',
  write_config: 'node-manager.cloudregion.node.installerStepWriteConfig',
  configure_runtime:
    'node-manager.cloudregion.node.installerStepWriteConfig',
  install: 'node-manager.cloudregion.node.installerStepInstall',
  run_package_installer:
    'node-manager.cloudregion.node.installerStepInstall',
  install_complete: 'node-manager.cloudregion.node.installerStepComplete',
  complete: 'node-manager.cloudregion.node.installerStepComplete'
};

export const INSTALLER_STEP_SUGGESTION_KEYS: InstallerStepLabelMap = {
  fetch_session: 'node-manager.cloudregion.node.installerSuggestionFetchSession',
  prepare_dirs: 'node-manager.cloudregion.node.installerSuggestionPrepareDirs',
  prepare_directories:
    'node-manager.cloudregion.node.installerSuggestionPrepareDirs',
  download: 'node-manager.cloudregion.node.installerSuggestionDownload',
  download_package: 'node-manager.cloudregion.node.installerSuggestionDownload',
  extract: 'node-manager.cloudregion.node.installerSuggestionExtract',
  extract_package: 'node-manager.cloudregion.node.installerSuggestionExtract',
  write_config: 'node-manager.cloudregion.node.installerSuggestionWriteConfig',
  configure_runtime:
    'node-manager.cloudregion.node.installerSuggestionWriteConfig',
  install: 'node-manager.cloudregion.node.installerSuggestionInstall',
  run_package_installer:
    'node-manager.cloudregion.node.installerSuggestionInstall'
};

export const INSTALLER_FAILURE_SUGGESTION_KEYS: Partial<Record<InstallerFailureType, string>> = {
  object_missing: 'node-manager.cloudregion.node.installerSuggestionObjectMissing',
  bucket_missing: 'node-manager.cloudregion.node.installerSuggestionBucketMissing',
  connection: 'node-manager.cloudregion.node.installerSuggestionConnection',
  timeout: 'node-manager.cloudregion.node.installerSuggestionTimeout',
  auth: 'node-manager.cloudregion.node.installerSuggestionAuth',
  permission: 'node-manager.cloudregion.node.installerSuggestionPermission',
  file_busy: 'node-manager.cloudregion.node.installerSuggestionFileBusy',
  disk: 'node-manager.cloudregion.node.installerSuggestionDisk',
  package_invalid: 'node-manager.cloudregion.node.installerSuggestionPackageInvalid',
  arch_mismatch: 'node-manager.cloudregion.node.installerSuggestionArchMismatch'
};

export const INSTALLER_FAILURE_CONTEXT_LABEL_KEYS: Partial<Record<keyof InstallerFailureContext, string>> = {
  bucket: 'node-manager.cloudregion.node.failureContextBucket',
  file_key: 'node-manager.cloudregion.node.failureContextFileKey',
  package_name: 'node-manager.cloudregion.node.failureContextPackageName',
  cpu_architecture: 'node-manager.cloudregion.node.failureContextArchitecture',
  install_dir: 'node-manager.cloudregion.node.failureContextInstallDir',
  target_path: 'node-manager.cloudregion.node.failureContextTargetPath',
  exit_code: 'node-manager.cloudregion.node.failureContextExitCode'
};

export const formatInstallerProgressValue = (value?: number, unit?: string) => {
  const normalizedValue = normalizeNumber(value);

  if (normalizedValue === null) {
    return null;
  }

  if (unit === 'bytes') {
    if (normalizedValue === 0) {
      return '0 B';
    }

    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const base = Math.min(
      Math.floor(Math.log(normalizedValue) / Math.log(1024)),
      units.length - 1
    );
    const formatted = normalizedValue / 1024 ** base;
    return `${formatted >= 10 ? formatted.toFixed(0) : formatted.toFixed(1)} ${units[base]}`;
  }

  return `${normalizedValue}`;
};

export const getInstallerProgressPercent = (
  progress?: InstallerProgressMetric
) => {
  const normalizedProgress = normalizeProgress(progress);

  if (normalizedProgress?.percent !== null && normalizedProgress?.percent !== undefined) {
    return normalizedProgress.percent;
  }

  if (
    normalizedProgress?.current !== null &&
    normalizedProgress?.current !== undefined &&
    normalizedProgress?.total !== null &&
    normalizedProgress?.total !== undefined &&
    normalizedProgress.total > 0
  ) {
    return clampNumber(
      Math.round((normalizedProgress.current / normalizedProgress.total) * 100),
      0,
      100
    );
  }

  return null;
};

export const getInstallerProgressText = (progress?: InstallerProgressMetric) => {
  const normalizedProgress = normalizeProgress(progress);

  if (!normalizedProgress) {
    return null;
  }

  if (
    normalizedProgress.current !== null &&
    normalizedProgress.current !== undefined &&
    normalizedProgress.total !== null &&
    normalizedProgress.total !== undefined
  ) {
    const current = formatInstallerProgressValue(
      normalizedProgress.current,
      normalizedProgress.unit || undefined
    );
    const total = formatInstallerProgressValue(
      normalizedProgress.total,
      normalizedProgress.unit || undefined
    );

    if (current && total) {
      return `${current} / ${total}`;
    }
  }

  const percent = getInstallerProgressPercent(progress);
  if (percent !== null) {
    return `${percent}%`;
  }

  if (
    normalizedProgress.current !== null &&
    normalizedProgress.current !== undefined
  ) {
    return formatInstallerProgressValue(
      normalizedProgress.current,
      normalizedProgress.unit || undefined
    );
  }

  return null;
};

export const getInstallerStepInfo = (
  stepIndex?: number,
  stepTotal?: number
) => {
  const normalizedStepIndex = normalizeNumber(stepIndex);
  const normalizedStepTotal = normalizeNumber(stepTotal);

  if (
    normalizedStepIndex !== null &&
    normalizedStepTotal !== null &&
    normalizedStepIndex > 0 &&
    normalizedStepTotal > 0
  ) {
    return `${Math.min(Math.round(normalizedStepIndex), Math.round(normalizedStepTotal))}/${Math.round(normalizedStepTotal)}`;
  }

  return null;
};

export const getInstallerStepLabel = (
  t: TranslationFunction,
  step?: InstallerStepCode,
  fallback?: string
) => {
  if (step && INSTALLER_STEP_LABEL_KEYS[step]) {
    return t(INSTALLER_STEP_LABEL_KEYS[step]);
  }

  return normalizeText(fallback) || normalizeText(step) || '--';
};

export const getInstallerFailureSuggestion = (
  t: TranslationFunction,
  step?: InstallerStepCode
) => {
  if (step && INSTALLER_STEP_SUGGESTION_KEYS[step]) {
    return t(INSTALLER_STEP_SUGGESTION_KEYS[step]);
  }

  return t('node-manager.cloudregion.node.installerSuggestionGeneric');
};

export const getInstallerFailureSuggestionByType = (
  t: TranslationFunction,
  failureType?: InstallerFailureType | null
) => {
  if (failureType && INSTALLER_FAILURE_SUGGESTION_KEYS[failureType]) {
    return t(INSTALLER_FAILURE_SUGGESTION_KEYS[failureType]);
  }

  return null;
};

export const getInstallerSummaryGuidance = (
  t: TranslationFunction,
  summary?: InstallerEventSummary | null
) => {
  const state = normalizeText(summary?.state);
  const guidanceKeyMap: Record<string, string> = {
    no_installer_events:
      'node-manager.cloudregion.node.installerSummaryNoEvents',
    incomplete_installer_events:
      'node-manager.cloudregion.node.installerSummaryIncomplete',
    installer_success_connectivity_pending:
      'node-manager.cloudregion.node.installerSummaryConnectivityPending',
    installer_success_connectivity_timeout:
      'node-manager.cloudregion.node.installerSummaryConnectivityTimeout',
    duplicated_events:
      'node-manager.cloudregion.node.installerSummaryDuplicatedEvents'
  };

  if (state && guidanceKeyMap[state]) {
    return t(guidanceKeyMap[state]);
  }

  const anomaly = summary?.anomalies?.find((item) => guidanceKeyMap[item]);
  if (anomaly) {
    return t(guidanceKeyMap[anomaly]);
  }

  return null;
};

const getInstallerFailureContextEntries = (
  t: TranslationFunction,
  context?: InstallerFailureContext
) => {
  if (!context) {
    return [];
  }

  return Object.entries(context)
    .map(([key, value]) => {
      if (value === null || value === undefined || value === '') {
        return null;
      }

      const labelKey = INSTALLER_FAILURE_CONTEXT_LABEL_KEYS[key as keyof InstallerFailureContext];
      const label = labelKey ? t(labelKey) : key;
      return `${label}: ${value}`;
    })
    .filter((entry): entry is string => Boolean(entry));
};

export const getFailedInstallerStep = (steps?: LogStep[]) => {
  if (!steps?.length) {
    return null;
  }

  return [...steps]
    .reverse()
    .find((step) => ['error', 'timeout'].includes(step.status));
};

export const getInstallerFailureGuidance = (
  t: TranslationFunction,
  result?: OperationTaskResult | null
) => {
  const failedStep = getFailedInstallerStep(result?.steps);
  const rawStep = failedStep?.details?.raw_step || failedStep?.action;
  const failure = failedStep?.details?.failure || result?.failure;

  const reason = normalizeText(
    failure?.summary ||
      failure?.message ||
      failedStep?.details?.error ||
      failedStep?.message ||
      result?.installer_progress?.current_message ||
      null
  );

  const contextEntries = getInstallerFailureContextEntries(t, failure?.context);

  return {
    reason,
    context: contextEntries,
    suggestion:
      getInstallerFailureSuggestionByType(t, failure?.type) ||
      getInstallerFailureSuggestion(t, rawStep)
  };
};

export const getInstallerSummaryLabel = (
  t: TranslationFunction,
  installerProgress?: InstallerProgressSummary | null
) => {
  if (!installerProgress) {
    return null;
  }

  return getInstallerStepLabel(
    t,
    installerProgress.current_step,
    installerProgress.current_message || installerProgress.current_step
  );
};
