import {
  createPasswordFieldLabels,
  createPasswordValidationRuleLabels,
  passwordLockInputPrefix,
} from '@/components/security/password-form-modal/presets';

export const securityPasswordInputPrefix = passwordLockInputPrefix;

export const securityPasswordFieldLabels = createPasswordFieldLabels({
  passwordLabel: 'New password',
  passwordPlaceholder: 'Enter a new password',
  confirmLabel: 'Confirm password',
  confirmPlaceholder: 'Enter the password again',
  requiredMessage: 'Password is required',
  mismatchMessage: 'Passwords do not match',
  temporaryLabel: 'Temporary password',
  temporaryTooltip: 'Require a reset on next login',
});

export const securityPasswordValidator = async () => undefined;

export const securityPasswordPolicy = {
  minLength: 10,
  maxLength: 20,
  requiredCharTypes: ['uppercase', 'lowercase', 'digit'] as const,
};

export const securityStrictPasswordPolicy = {
  minLength: 10,
  maxLength: 20,
  requiredCharTypes: ['uppercase', 'lowercase', 'digit', 'special'] as const,
};

export const securityPasswordValidationHint = {
  validationHintTitle: 'Password requirements',
  validationRuleLabels: createPasswordValidationRuleLabels({
    length: 'Length: 10-20',
    uppercase: 'Uppercase letter',
    lowercase: 'Lowercase letter',
    digit: 'Number',
  }),
  validationStatus: {
    length: true,
    uppercase: true,
    lowercase: true,
    digit: false,
    special: false,
  },
};
