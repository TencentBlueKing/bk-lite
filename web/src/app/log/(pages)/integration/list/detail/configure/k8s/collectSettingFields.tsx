'use client';

import React, { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, Radio } from 'antd';
import { useTranslation } from '@/utils/i18n';
import FieldGuideTip from '@/components/field-guide-tip';
import FormSettingRow from '@/components/form-setting-row';

export const K8S_SETTING_FORM_WIDTH = 300;
export const MAX_PATTERNS_PER_DIMENSION = 50;
export const MAX_INCLUDE_PATTERNS = 200;
const PATTERN_WHITELIST = /^[a-z0-9.*?-]+$/;

export const FieldLabel: React.FC<{ label: string; detail?: string }> = ({
  label,
  detail
}) => {
  const { t } = useTranslation();
  return (
    <span className="inline-flex items-center">
      {label}
      <FieldGuideTip
        short={detail}
        title={t('log.integration.k8s.fieldGuideTip')}
      />
    </span>
  );
};

const parsePatternLines = (value: unknown): string[] => {
  const lines: string[] = [];
  const seen = new Set<string>();
  for (const item of String(value || '').split('\n')) {
    const line = item.trim();
    if (!line || seen.has(line)) {
      continue;
    }
    seen.add(line);
    lines.push(line);
  }
  return lines;
};

export const expandedIncludePatternCount = (
  namespaceValue: unknown,
  podValue: unknown
) => {
  const namespaces = parsePatternLines(namespaceValue);
  const pods = parsePatternLines(podValue);
  if (!namespaces.length && !pods.length) {
    return 0;
  }
  return (namespaces.length || 1) * (pods.length || 1);
};

export const validateK8sCollectPatterns = (
  value: unknown,
  t: (key: string) => string
) => {
  const lines = parsePatternLines(value);
  if (lines.length > MAX_PATTERNS_PER_DIMENSION) {
    return Promise.reject(new Error(t('log.integration.k8s.patternLimit')));
  }
  for (const line of lines) {
    if (line.includes('_')) {
      return Promise.reject(
        new Error(t('log.integration.k8s.patternNoUnderscore'))
      );
    }
    if (line.includes('**')) {
      return Promise.reject(
        new Error(t('log.integration.k8s.patternNoDoubleStar'))
      );
    }
    if (/[A-Z]/.test(line)) {
      return Promise.reject(
        new Error(t('log.integration.k8s.patternNoUppercase'))
      );
    }
    if (!PATTERN_WHITELIST.test(line)) {
      return Promise.reject(
        new Error(t('log.integration.k8s.patternCharset'))
      );
    }
  }
  return Promise.resolve();
};

const validateK8sCollectExpansion = (
  namespaceValue: unknown,
  podValue: unknown,
  t: (key: string) => string
) => {
  if (
    expandedIncludePatternCount(namespaceValue, podValue) > MAX_INCLUDE_PATTERNS
  ) {
    return Promise.reject(
      new Error(t('log.integration.k8s.patternExpandedLimit'))
    );
  }
  return Promise.resolve();
};

interface CollectSettingFieldsProps {
  unknown?: boolean;
  initialDockerPath?: string;
}

const CollectSettingFields: React.FC<CollectSettingFieldsProps> = ({
  unknown = false,
  initialDockerPath
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const [showDockerAdvanced, setShowDockerAdvanced] = useState(
    Boolean(String(initialDockerPath || '').trim())
  );

  useEffect(() => {
    setShowDockerAdvanced(Boolean(String(initialDockerPath || '').trim()));
  }, [initialDockerPath]);

  const validatePatternField = (field: 'namespace_patterns' | 'pod_patterns') =>
    (_: unknown, value: unknown) =>
      validateK8sCollectPatterns(value, t).then(() =>
        validateK8sCollectExpansion(
          field === 'namespace_patterns'
            ? value
            : form.getFieldValue('namespace_patterns'),
          field === 'pod_patterns' ? value : form.getFieldValue('pod_patterns'),
          t
        )
      );

  return (
    <>
      {unknown ? (
        <Alert
          type="warning"
          showIcon
          className="mb-4"
          message={t('log.integration.k8s.settingUnknownTitle')}
          description={t('log.integration.k8s.settingUnknownDesc')}
        />
      ) : null}

      <Form.Item
        label={
          <FieldLabel
            label={t('log.integration.k8s.runtimeProfile')}
            detail={t('log.integration.k8s.runtimeProfileDesc')}
          />
        }
        required
      >
        <FormSettingRow
          control={
            <Form.Item
              name="runtime_profile"
              noStyle
              rules={[{ required: true, message: t('common.required') }]}
            >
              <Radio.Group className="w-[300px]">
                <Radio value="standard">
                  {t('log.integration.k8s.runtimeProfileStandard')}
                </Radio>
                <Radio value="docker">
                  {t('log.integration.k8s.runtimeProfileDocker')}
                </Radio>
                <Radio value="custom">
                  {t('log.integration.k8s.runtimeProfileCustom')}
                </Radio>
              </Radio.Group>
            </Form.Item>
          }
          description={t('log.integration.k8s.runtimeProfileHint')}
        />
      </Form.Item>

      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.runtime_profile !== currentValues.runtime_profile
        }
      >
        {({ getFieldValue }) =>
          getFieldValue('runtime_profile') === 'custom' ? (
            <>
              <Form.Item
                label={
                  <FieldLabel
                    label={t('log.integration.k8s.hostLogPath')}
                    detail={t('log.integration.k8s.hostLogPathDesc')}
                  />
                }
                required
              >
                <FormSettingRow
                  control={
                    <Form.Item
                      name="host_log_path"
                      noStyle
                      rules={[
                        { required: true, message: t('common.required') },
                        {
                          validator: (_, value) => {
                            if (!value || String(value).startsWith('/')) {
                              return Promise.resolve();
                            }
                            return Promise.reject(
                              new Error(
                                t('log.integration.k8s.absolutePathRequired')
                              )
                            );
                          }
                        }
                      ]}
                    >
                      <Input
                        placeholder={t(
                          'log.integration.k8s.hostLogPathPlaceholder'
                        )}
                        className="w-[300px]"
                      />
                    </Form.Item>
                  }
                  description={t('log.integration.k8s.hostLogPathHint')}
                />
              </Form.Item>

              <Button
                type="link"
                className="px-0 mb-3"
                onClick={() => setShowDockerAdvanced((prev) => !prev)}
              >
                {showDockerAdvanced
                  ? t('log.integration.k8s.hideDockerAdvanced')
                  : t('log.integration.k8s.showDockerAdvanced')}
              </Button>

              {showDockerAdvanced ? (
                <Form.Item
                  label={
                    <FieldLabel
                      label={t('log.integration.k8s.dockerContainerLogPath')}
                      detail={t(
                        'log.integration.k8s.dockerContainerLogPathDesc'
                      )}
                    />
                  }
                >
                  <FormSettingRow
                    control={
                      <Form.Item
                        name="docker_container_log_path"
                        noStyle
                        rules={[
                          {
                            validator: (_, value) => {
                              if (!value || String(value).startsWith('/')) {
                                return Promise.resolve();
                              }
                              return Promise.reject(
                                new Error(
                                  t('log.integration.k8s.absolutePathRequired')
                                )
                              );
                            }
                          }
                        ]}
                      >
                        <Input
                          placeholder={t(
                            'log.integration.k8s.dockerContainerLogPathPlaceholder'
                          )}
                          className="w-[300px]"
                        />
                      </Form.Item>
                    }
                    description={t(
                      'log.integration.k8s.dockerContainerLogPathHint'
                    )}
                  />
                </Form.Item>
              ) : null}
            </>
          ) : null
        }
      </Form.Item>

      <Form.Item
        label={
          <FieldLabel
            label={t('log.integration.k8s.collectNamespace')}
            detail={t('log.integration.k8s.collectNamespaceDesc')}
          />
        }
      >
        <FormSettingRow
          control={
            <Form.Item
              name="namespace_patterns"
              noStyle
              dependencies={['pod_patterns']}
              rules={[{ validator: validatePatternField('namespace_patterns') }]}
            >
              <Input.TextArea
                rows={3}
                placeholder={t(
                  'log.integration.k8s.collectNamespacePlaceholder'
                )}
                className="w-[300px]"
              />
            </Form.Item>
          }
          description={t('log.integration.k8s.collectNamespaceHint')}
        />
      </Form.Item>

      <Form.Item
        label={
          <FieldLabel
            label={t('log.integration.k8s.collectPod')}
            detail={t('log.integration.k8s.collectPodDesc')}
          />
        }
      >
        <FormSettingRow
          control={
            <Form.Item
              name="pod_patterns"
              noStyle
              dependencies={['namespace_patterns']}
              rules={[{ validator: validatePatternField('pod_patterns') }]}
            >
              <Input.TextArea
                rows={3}
                placeholder={t('log.integration.k8s.collectPodPlaceholder')}
                className="w-[300px]"
              />
            </Form.Item>
          }
          description={t('log.integration.k8s.collectPodHint')}
        />
      </Form.Item>
    </>
  );
};

export default CollectSettingFields;
