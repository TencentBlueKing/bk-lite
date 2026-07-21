import type {
  ConflictAction,
  SecretSupplement,
  WarningItem,
} from '../../api/importExport';

export const SECRET_PLACEHOLDER_WARNING_CODE = 'OA_SECRET_PLACEHOLDER';

export type ConflictDecisions = Record<string, ConflictAction>;
export type SecretSupplementValues = Record<string, string>;

export const getSecretSupplementKey = (warning: WarningItem) => {
  if (!warning.object_key || !warning.field) return null;
  return JSON.stringify([warning.object_key, warning.field]);
};

const isValidSecretSupplementValue = (value: string | undefined): value is string => (
  !!value?.trim() && value !== '******'
);

export const getVisibleImportWarnings = (
  warnings: WarningItem[],
  conflictDecisions: ConflictDecisions,
) => warnings.filter((warning) => (
  !warning.object_key || conflictDecisions[warning.object_key] !== 'skip'
));

export const hasBlockingImportWarnings = (
  warnings: WarningItem[],
  conflictDecisions: ConflictDecisions,
  secretSupplementValues: SecretSupplementValues,
) => getVisibleImportWarnings(warnings, conflictDecisions).some((warning) => {
  if (warning.code !== SECRET_PLACEHOLDER_WARNING_CODE) return true;
  if (warning.object_key && conflictDecisions[warning.object_key] === 'overwrite') {
    return false;
  }

  const key = getSecretSupplementKey(warning);
  return !key || !isValidSecretSupplementValue(secretSupplementValues[key]);
});

export const buildSecretSupplements = (
  warnings: WarningItem[],
  conflictDecisions: ConflictDecisions,
  secretSupplementValues: SecretSupplementValues,
): SecretSupplement[] => getVisibleImportWarnings(warnings, conflictDecisions)
  .filter((warning) => warning.code === SECRET_PLACEHOLDER_WARNING_CODE)
  .flatMap((warning) => {
    const key = getSecretSupplementKey(warning);
    const value = key ? secretSupplementValues[key] : undefined;
    if (
      !key
      || !isValidSecretSupplementValue(value)
      || !warning.object_key
      || !warning.field
    ) return [];
    return [{
      object_key: warning.object_key,
      field: warning.field,
      value,
    }];
  });
