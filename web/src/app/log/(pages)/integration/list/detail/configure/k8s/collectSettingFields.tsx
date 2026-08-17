'use client';

import React, { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, Radio, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

export const K8S_SETTING_FORM_WIDTH = 300;
const PATTERN_WHITELIST = /^[a-z0-9.*?-]+$/;

export const FieldHint: React.FC<{ hint: string }> = ({ hint }) => (
  <div className="flex-1 text-[var(--color-text-3)]">{hint}</div>
);

const FieldGuideTip: React.FC<{ detail?: string }> = ({ detail }) => {
  const { t } = useTranslation();

  if (!detail) {
    return null;
  }

  return (
    <Tooltip
      placement="top"
      mouseEnterDelay={0.15}
      color="var(--color-bg)"
      overlayInnerStyle={{
        maxWidth: 420,
        padding: '10px 12px',
        color: 'var(--color-text-1)',
        border: '1px solid var(--color-border-1)',
        boxShadow: '0 6px 16px rgba(0, 0, 0, 0.08)',
        borderRadius: 8
      }}
      title={
        <div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: 'var(--color-text-1)',
              marginBottom: 4
            }}
          >
            {t('log.integration.k8s.fieldGuideTip')}
          </div>
          <div
            style={{
              fontSize: 12,
              lineHeight: '20px',
              color: 'var(--color-text-2)',
              whiteSpace: 'pre-line'
            }}
          >
            {detail}
          </div>
        </div>
      }
    >
      <button
        type="button"
        aria-label={t('log.integration.k8s.fieldGuideTip')}
        className="inline-flex items-center justify-center ml-[4px] align-middle w-[18px] h-[18px] rounded-full text-[var(--color-text-3)] hover:text-[var(--color-primary)] hover:bg-[var(--color-fill-2)] transition-colors duration-150 cursor-help border-0 bg-transparent p-0"
        onClick={(e) => e.preventDefault()}
      >
        <QuestionCircleOutlined className="text-[13px]" />
      </button>
    </Tooltip>
  );
};

export const FieldLabel: React.FC<{ label: string; detail?: string }> = ({
  label,
  detail
}) => (
  <span className="inline-flex items-center">
    {label}
    <FieldGuideTip detail={detail} />
  </span>
);

export const validateK8sCollectPatterns = (
  value: unknown,
  t: (key: string) => string
) => {
  const lines = String(value || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
  if (lines.length > 50) {
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

interface CollectSettingFieldsProps {
  unknown?: boolean;
  initialDockerPath?: string;
}

const CollectSettingFields: React.FC<CollectSettingFieldsProps> = ({
  unknown = false,
  initialDockerPath
}) => {
  const { t } = useTranslation();
  const [showDockerAdvanced, setShowDockerAdvanced] = useState(
    Boolean(String(initialDockerPath || '').trim())
  );

  useEffect(() => {
    setShowDockerAdvanced(Boolean(String(initialDockerPath || '').trim()));
  }, [initialDockerPath]);

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
        <div className="flex items-start gap-4">
          <Form.Item
            name="runtime_profile"
            noStyle
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Radio.Group style={{ width: K8S_SETTING_FORM_WIDTH }}>
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
          <FieldHint hint={t('log.integration.k8s.runtimeProfileHint')} />
        </div>
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
                <div className="flex items-start gap-4">
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
                      style={{ width: K8S_SETTING_FORM_WIDTH }}
                    />
                  </Form.Item>
                  <FieldHint hint={t('log.integration.k8s.hostLogPathHint')} />
                </div>
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
                  <div className="flex items-start gap-4">
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
                        style={{ width: K8S_SETTING_FORM_WIDTH }}
                      />
                    </Form.Item>
                    <FieldHint
                      hint={t('log.integration.k8s.dockerContainerLogPathHint')}
                    />
                  </div>
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
        <div className="flex items-start gap-4">
          <Form.Item
            name="namespace_patterns"
            noStyle
            rules={[
              {
                validator: (_, value) => validateK8sCollectPatterns(value, t)
              }
            ]}
          >
            <Input.TextArea
              rows={3}
              placeholder={t(
                'log.integration.k8s.collectNamespacePlaceholder'
              )}
              style={{ width: K8S_SETTING_FORM_WIDTH }}
            />
          </Form.Item>
          <FieldHint hint={t('log.integration.k8s.collectNamespaceHint')} />
        </div>
      </Form.Item>

      <Form.Item
        label={
          <FieldLabel
            label={t('log.integration.k8s.collectPod')}
            detail={t('log.integration.k8s.collectPodDesc')}
          />
        }
      >
        <div className="flex items-start gap-4">
          <Form.Item
            name="pod_patterns"
            noStyle
            rules={[
              {
                validator: (_, value) => validateK8sCollectPatterns(value, t)
              }
            ]}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('log.integration.k8s.collectPodPlaceholder')}
              style={{ width: K8S_SETTING_FORM_WIDTH }}
            />
          </Form.Item>
          <FieldHint hint={t('log.integration.k8s.collectPodHint')} />
        </div>
      </Form.Item>
    </>
  );
};

export default CollectSettingFields;
