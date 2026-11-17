'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const KNOWN_CHAR_TYPES = ['uppercase', 'lowercase', 'digit', 'special'] as const;

export interface PasswordPolicyConfig {
  min_length?: number;
  max_length?: number;
  require_uppercase?: boolean;
  require_lowercase?: boolean;
  require_digit?: boolean;
  require_special?: boolean;
  pwd_set_min_length?: string | number;
  pwd_set_max_length?: string | number;
  pwd_set_required_char_types?: string | string[];
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

function parseLength(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function usesSystemPasswordSettings(policy: PasswordPolicyConfig): boolean {
  return 'pwd_set_min_length' in policy || 'pwd_set_max_length' in policy;
}

function readLengths(policy: PasswordPolicyConfig | null, minFallback: number) {
  if (policy && usesSystemPasswordSettings(policy)) {
    return {
      minLength: parseLength(policy.pwd_set_min_length, minFallback),
      maxLength: parseLength(policy.pwd_set_max_length, 20),
    };
  }
  const maxLength = policy?.max_length;
  return {
    minLength: parseLength(policy?.min_length, minFallback),
    maxLength: typeof maxLength === 'number' && Number.isFinite(maxLength) ? maxLength : undefined,
  };
}

function readRequiredCharTypes(policy: PasswordPolicyConfig | null): string[] {
  const raw = policy?.pwd_set_required_char_types;
  const tokens = typeof raw === 'string' ? raw.split(',') : Array.isArray(raw) ? raw : null;
  if (tokens) {
    const types = tokens
      .map((item) => String(item).trim())
      .filter((item) => (KNOWN_CHAR_TYPES as readonly string[]).includes(item));
    if (types.length > 0) {
      return types;
    }
  }
  if (policy?.require_special) {
    return ['uppercase', 'lowercase', 'digit', 'special'];
  }
  if (policy?.require_digit) {
    return ['uppercase', 'lowercase', 'digit'];
  }
  return ['uppercase', 'lowercase'];
}

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
  const fetchPolicyRef = useRef(fetchPolicy);
  fetchPolicyRef.current = fetchPolicy;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    // 调用方每次渲染都会传入新的 fetchPolicy。放进依赖后，setPolicy 触发的渲染会再次请求。
    fetchPolicyRef.current()
      .then((data) => {
        if (!cancelled) setPolicy(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  const validatePassword = useCallback(
    async (password: string): Promise<void> => {
      const failedRules: string[] = [];
      const { minLength: effectiveMin, maxLength } = readLengths(policy, minLength);
      const status: PasswordValidationStatus = { passed: true };
      if (password.length < effectiveMin || (maxLength !== undefined && password.length > maxLength)) {
        status.length = 'min_length';
        failedRules.push('min_length');
      }
      const requiredTypes = new Set(readRequiredCharTypes(policy));
      if (requiredTypes.has('uppercase') && !/[A-Z]/.test(password)) {
        status.uppercase = 'require_uppercase';
        failedRules.push('require_uppercase');
      }
      if (requiredTypes.has('lowercase') && !/[a-z]/.test(password)) {
        status.lowercase = 'require_lowercase';
        failedRules.push('require_lowercase');
      }
      if (requiredTypes.has('digit') && !/\d/.test(password)) {
        status.digit = 'require_digit';
        failedRules.push('require_digit');
      }
      if (requiredTypes.has('special') && !/[^A-Za-z0-9]/.test(password)) {
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

  const lengths = readLengths(policy, minLength);

  return {
    policy,
    loading,
    rulesLoading: loading,
    minLength: lengths.minLength,
    maxLength: lengths.maxLength,
    requiredCharTypes: readRequiredCharTypes(policy),
    validatePassword,
    resetValidation,
    updateValidationStatus,
    validationStatus,
    PasswordPolicySettings,
  };
};

export default usePasswordPolicy;
