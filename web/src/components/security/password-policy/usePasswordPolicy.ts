'use client';

import { useEffect, useState, useCallback } from 'react';

export interface PasswordPolicyConfig {
  min_length?: number;
  max_length?: number;
  require_uppercase?: boolean;
  require_lowercase?: boolean;
  require_digit?: boolean;
  require_special?: boolean;
  [key: string]: unknown;
}

export interface PasswordValidationStatus {
  passed: boolean;
  message?: string;
  failedRules?: string[];
  length?: string;
  uppercase?: string;
  lowercase?: string;
  digit?: string;
  special?: string;
  [ruleKey: string]: boolean | string | string[] | undefined;
}

export type PasswordPolicySettings = PasswordPolicyConfig;

export const PasswordPolicySettings = {} as PasswordPolicyConfig;

export interface UsePasswordPolicyOptions {
  enabled?: boolean;
  fetchPolicy: () => Promise<PasswordPolicyConfig>;
  minLength?: number;
}

export interface UsePasswordPolicyReturn {
  policy: PasswordPolicyConfig | null;
  loading: boolean;
  rulesLoading: boolean;
  minLength: number;
  maxLength: number | undefined;
  requiredCharTypes: string[];
  validatePassword: (password: string) => Promise<void>;
  resetValidation: () => void;
  updateValidationStatus: (status: Partial<PasswordValidationStatus>) => void;
  validationStatus: PasswordValidationStatus;
  PasswordPolicySettings: typeof PasswordPolicySettings;
}

export const usePasswordPolicy = ({
  enabled = true,
  fetchPolicy,
  minLength = 8,
}: UsePasswordPolicyOptions): UsePasswordPolicyReturn => {
  const [policy, setPolicy] = useState<PasswordPolicyConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [validationStatus, setValidationStatus] = useState<PasswordValidationStatus>({ passed: true });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    fetchPolicy()
      .then((data) => {
        if (!cancelled) setPolicy(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, fetchPolicy]);

  const validatePassword = useCallback(
    async (password: string): Promise<void> => {
      const failedRules: string[] = [];
      const effectiveMin = (policy?.min_length as number | undefined) ?? minLength;
      const status: PasswordValidationStatus = { passed: true };
      if (password.length < effectiveMin) {
        status.length = 'min_length';
        failedRules.push('min_length');
      }
      if (policy?.require_uppercase && !/[A-Z]/.test(password)) {
        status.uppercase = 'require_uppercase';
        failedRules.push('require_uppercase');
      }
      if (policy?.require_lowercase && !/[a-z]/.test(password)) {
        status.lowercase = 'require_lowercase';
        failedRules.push('require_lowercase');
      }
      if (policy?.require_digit && !/\d/.test(password)) {
        status.digit = 'require_digit';
        failedRules.push('require_digit');
      }
      if (policy?.require_special && !/[^A-Za-z0-9]/.test(password)) {
        status.special = 'require_special';
        failedRules.push('require_special');
      }
      status.passed = failedRules.length === 0;
      status.failedRules = failedRules;
      setValidationStatus(status);
    },
    [policy, minLength]
  );

  const resetValidation = useCallback(() => {
    setValidationStatus({ passed: true });
  }, []);

  const updateValidationStatus = useCallback((status: Partial<PasswordValidationStatus>) => {
    setValidationStatus((prev) => ({ ...prev, ...status }));
  }, []);

  const effectiveMin = (policy?.min_length as number | undefined) ?? minLength;

  return {
    policy,
    loading,
    rulesLoading: loading,
    minLength: effectiveMin,
    maxLength: policy?.max_length as number | undefined,
    requiredCharTypes: policy?.require_special
      ? ['uppercase', 'lowercase', 'digit', 'special']
      : policy?.require_digit
        ? ['uppercase', 'lowercase', 'digit']
        : ['uppercase', 'lowercase'],
    validatePassword,
    resetValidation,
    updateValidationStatus,
    validationStatus,
    PasswordPolicySettings,
  };
};

export default usePasswordPolicy;
