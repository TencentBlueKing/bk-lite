import { LockOutlined } from '@ant-design/icons';
import type { PasswordValidationStatus } from '@/components/security/password-policy/usePasswordPolicy';

export interface PasswordFieldLabelsConfig {
  confirmLabel: string;
  confirmPlaceholder: string;
  mismatchMessage: string;
  passwordLabel: string;
  passwordPlaceholder: string;
  requiredMessage: string;
  temporaryLabel?: string;
  temporaryTooltip?: string;
}

export interface PasswordValidationLabelsConfig {
  digit?: string;
  length: string;
  lowercase?: string;
  special?: string;
  uppercase?: string;
}

export const passwordLockInputPrefix = <LockOutlined />;

export const createPasswordFieldLabels = (
  config: PasswordFieldLabelsConfig,
) => ({
  confirmLabel: config.confirmLabel,
  confirmPlaceholder: config.confirmPlaceholder,
  mismatchMessage: config.mismatchMessage,
  passwordLabel: config.passwordLabel,
  passwordPlaceholder: config.passwordPlaceholder,
  requiredMessage: config.requiredMessage,
  temporaryLabel: config.temporaryLabel,
  temporaryTooltip: config.temporaryTooltip,
});

export const createPasswordValidationRuleLabels = (
  config: PasswordValidationLabelsConfig,
): Partial<Record<keyof PasswordValidationStatus, string>> => ({
  length: config.length,
  uppercase: config.uppercase,
  lowercase: config.lowercase,
  digit: config.digit,
  special: config.special,
});
