'use client';

import React, { useMemo } from 'react';
import { Alert, Button, Descriptions, Empty } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useCopy } from '@/hooks/useCopy';
import {
  AlertSourceIntegrationGuide,
  IntegrationGuideFieldMappingItem,
  IntegrationGuideParameterMappingItem,
  IntegrationGuideStepItem,
  IntegrationGuideTroubleshootingItem,
  IntegrationGuideVerificationCheck,
} from '@/app/alarm/types/integration';

interface ZabbixGuideProps {
  guide?: AlertSourceIntegrationGuide;
  credentialsSlot?: React.ReactNode;
  selectedTeamSecret?: string;
}

const sectionClassName = 'overflow-hidden rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)]';
const sectionHeaderClassName = 'border-b border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_3%,var(--color-bg-1))] px-5 py-4';
const sectionBodyClassName = 'px-5 py-4';
const codeBlockClassName = 'relative overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-5 py-4';
const copyIconClassName = 'absolute top-4 right-4 cursor-pointer text-[var(--color-text-3)] transition hover:text-[var(--color-primary)]';
const cardClassName = 'rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-4 py-3.5';

const zabbixParameterDefaults = {
  URL: 'guide.webhook_url',
  SECRET: 'guide.headers.SECRET',
  SOURCE_ID: 'guide.source_id',
  Subject: '{ALERT.SUBJECT}',
  Message: '{ALERT.MESSAGE}',
  Severity: '{EVENT.NSEVERITY}',
  TriggerName: '{TRIGGER.NAME}',
  ProblemId: '{EVENT.ID}',
  EventId: '{EVENT.ID}',
  RecoveryEventId: '{EVENT.RECOVERY.ID}',
  TriggerId: '{TRIGGER.ID}',
  HostId: '{HOST.ID}',
  HostName: '{HOST.NAME}',
  EventValue: '{EVENT.VALUE}',
  ResourceType: 'host',
} as const;

const zabbixParameterAliases: Record<string, keyof typeof zabbixParameterDefaults> = {
  webhook_url: 'URL',
  url: 'URL',
  secret: 'SECRET',
  source_id: 'SOURCE_ID',
};

interface ZabbixParameterRow {
  key: string;
  name: string;
  value: string;
  displayValue: string;
  description?: string;
  required?: boolean;
  copyable?: boolean;
}

const normalizeLegacyStepItem = (item: string | IntegrationGuideStepItem, index: number) => {
  if (typeof item === 'string') {
    return {
      key: `${index}-${item}`,
      title: item,
      description: '',
      content: '',
    };
  }

  return {
    key: `${index}-${item.title || item.description || item.content || 'item'}`,
    title: item.title || '',
    description: item.description || '',
    content: item.content || '',
  };
};

const normalizeTroubleshootingItem = (
  item: IntegrationGuideTroubleshootingItem | string | IntegrationGuideStepItem,
  index: number,
) => {
  if (typeof item === 'string') {
    return {
      key: `${index}-${item}`,
      symptom: item,
      causes: [],
      resolutions: [],
    };
  }

  if ('title' in item || 'description' in item || 'content' in item) {
    return {
      key: `${index}-${item.title || item.description || item.content || 'item'}`,
      symptom: item.title || item.description || '',
      causes: item.content ? [item.content] : [],
      resolutions: [],
    };
  }

  const troubleshootingItem = item as IntegrationGuideTroubleshootingItem;

  return {
    key: `${index}-${troubleshootingItem.symptom || troubleshootingItem.cause || troubleshootingItem.action || 'issue'}`,
    symptom: troubleshootingItem.symptom || '',
    causes: troubleshootingItem.possible_causes?.length
      ? troubleshootingItem.possible_causes
      : troubleshootingItem.cause
        ? [troubleshootingItem.cause]
        : [],
    resolutions: troubleshootingItem.resolutions?.length
      ? troubleshootingItem.resolutions
      : troubleshootingItem.action
        ? [troubleshootingItem.action]
        : [],
  };
};

const renderCheckContent = (check?: IntegrationGuideVerificationCheck) => {
  if (!check) {
    return null;
  }

  return (
    <>
      {check.summary ? (
        <div className="text-[12px] leading-5 text-[var(--color-text-2)]">{check.summary}</div>
      ) : null}
      {check.steps?.length ? (
        <ul className="mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
          {check.steps.map((step, index) => (
            <li key={`${step}-${index}`} className="flex gap-2">
              <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
              <span>{step}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {check.expected_results?.length ? (
        <div className="mt-3 rounded-[14px] border border-[color-mix(in_srgb,var(--color-success)_18%,var(--color-bg-1))] bg-[color-mix(in_srgb,var(--color-success)_8%,var(--color-bg-1))] px-3.5 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-success)]">
            Expected results
          </div>
          <ul className="mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
            {check.expected_results.map((result, index) => (
              <li key={`${result}-${index}`} className="flex gap-2">
                <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-success)]" />
                <span>{result}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
};

const ZabbixGuide: React.FC<ZabbixGuideProps> = ({ guide, credentialsSlot, selectedTeamSecret }) => {
  const { t } = useTranslation();
  const { copy } = useCopy();

  const sourceSecret = guide?.headers?.SECRET ? String(guide.headers.SECRET) : '';
  const effectiveSecret = selectedTeamSecret || '';
  const secretMasked = effectiveSecret ? '******************' : '';
  const secretPlaceholder = '<' + t('integration.selectTeamPlaceholder') + '>';
  const applyTeamSecret = (raw?: string) => {
    if (!raw) return raw || '';
    if (!effectiveSecret || !sourceSecret) return raw;
    return raw.split(sourceSecret).join(effectiveSecret);
  };

  const sourceWebhookUrl = guide?.webhook_url ? String(guide.webhook_url) : '';
  const browserOrigin = typeof window !== 'undefined' ? window.location.origin : '';
  const applyBrowserOrigin = (rawUrl?: string): string => {
    if (!rawUrl) return '';
    if (!browserOrigin) return rawUrl;
    try {
      const u = new URL(rawUrl);
      return `${browserOrigin}${u.pathname}${u.search}${u.hash}`;
    } catch {
      return rawUrl;
    }
  };
  const effectiveWebhookUrl = applyBrowserOrigin(sourceWebhookUrl);
  const applyEffectiveWebhookUrl = (raw?: string) => {
    if (!raw) return raw || '';
    if (!sourceWebhookUrl || !effectiveWebhookUrl) return raw;
    return raw.split(sourceWebhookUrl).join(effectiveWebhookUrl);
  };

  const setupSteps = useMemo(() => {
    if (guide?.setup_steps?.length) {
      return guide.setup_steps.map((step, index) => ({
        key: `${index}-${step.title || 'step'}`,
        title: step.title || t('integration.zabbixUnnamedStep'),
        items: step.items || [],
      }));
    }

    return (guide?.steps || []).map((item, index) => {
      const normalized = normalizeLegacyStepItem(item, index);
      return {
        key: normalized.key,
        title: normalized.title || t('integration.zabbixUnnamedStep'),
        items: [normalized.description, normalized.content].filter(Boolean),
      };
    });
  }, [guide?.setup_steps, guide?.steps, t]);

  const parameterGuidance = useMemo(() => {
    if (guide?.parameter_guidance?.length) {
      return guide.parameter_guidance;
    }

    if (guide?.parameter_mapping?.length) {
      return guide.parameter_mapping;
    }

    return (guide?.media_type_parameters || []).map<IntegrationGuideParameterMappingItem>((parameter) => ({
      parameter,
    }));
  }, [guide?.media_type_parameters, guide?.parameter_guidance, guide?.parameter_mapping]);

  const parameterRows = useMemo<ZabbixParameterRow[]>(() => {
    const guidanceMap = new Map<string, IntegrationGuideParameterMappingItem>();

    parameterGuidance.forEach((item) => {
      const rawName = item.name || item.parameter || item.field || '';
      const normalizedName = zabbixParameterAliases[rawName] || rawName;

      if (!normalizedName || !(normalizedName in zabbixParameterDefaults)) {
        return;
      }

      guidanceMap.set(normalizedName, item);
    });

    return Object.entries(zabbixParameterDefaults).map(([name, fallbackValue]) => {
      const guidance = guidanceMap.get(name);
      let value = guidance?.value?.trim();

      if (!value) {
        if (name === 'URL') {
          value = effectiveWebhookUrl;
        } else if (name === 'SECRET') {
          value = effectiveSecret;
        } else if (name === 'SOURCE_ID') {
          value = guide?.source_id || '';
        } else {
          value = fallbackValue;
        }
      } else if (name === 'SECRET' && effectiveSecret && sourceSecret && value.includes(sourceSecret)) {
        value = value.split(sourceSecret).join(effectiveSecret);
      } else if (name === 'URL' && sourceWebhookUrl && value.includes(sourceWebhookUrl)) {
        value = value.split(sourceWebhookUrl).join(effectiveWebhookUrl);
      }

      const isSecretRow = name === 'SECRET';
      const displayValue = isSecretRow
        ? (effectiveSecret ? '******************' : secretPlaceholder)
        : value;

      return {
        key: name,
        name,
        value,
        displayValue,
        description: guidance?.description,
        required: guidance?.required,
        copyable: isSecretRow ? Boolean(effectiveSecret) : Boolean(value),
      };
    });
  }, [guide?.headers, guide?.source_id, guide?.webhook_url, parameterGuidance, effectiveSecret, sourceSecret, secretPlaceholder, effectiveWebhookUrl, sourceWebhookUrl]);

  const fieldMappings = useMemo(() => {
    if (guide?.field_mappings?.length) {
      return guide.field_mappings;
    }

    return (guide?.parameter_mapping || []).map<IntegrationGuideFieldMappingItem>((item) => ({
      bk_lite_field: item.target_field || item.field,
      upstream_source: item.parameter || item.name || item.value,
    }));
  }, [guide?.field_mappings, guide?.parameter_mapping]);

  const troubleshootingItems = useMemo(
    () => (guide?.troubleshooting || []).map(normalizeTroubleshootingItem),
    [guide?.troubleshooting]
  );

  const verificationCards = useMemo(() => {
    if (Array.isArray(guide?.verification)) {
      return guide.verification.map((item, index) => {
        const normalized = normalizeLegacyStepItem(item, index);
        return {
          key: normalized.key,
          title: normalized.title || t('integration.zabbixCheckItem'),
          check: {
            summary: normalized.description,
            steps: normalized.content ? [normalized.content] : [],
          } as IntegrationGuideVerificationCheck,
        };
      });
    }

    const verification = guide?.verification;
    return [
      {
        key: 'curl-check',
        title: verification?.curl_check?.title || t('integration.zabbixCurlCheck'),
        check: verification?.curl_check,
      },
      {
        key: 'problem-check',
        title: verification?.problem_check?.title || t('integration.zabbixProblemCheck'),
        check: verification?.problem_check,
      },
      {
        key: 'recovery-check',
        title: verification?.recovery_check?.title || t('integration.zabbixRecoveryCheck'),
        check: verification?.recovery_check,
      },
    ].filter((item) => item.check);
  }, [guide?.verification, t]);

  if (!guide) {
    return <Empty description={t('common.noData')} />;
  }

  const descriptionItems = [
    {
      key: 'webhook-url',
      label: t('integration.zabbixWebhookUrl'),
      value: effectiveWebhookUrl,
      display: effectiveWebhookUrl,
      copyable: true,
      masked: false,
    },
    {
      key: 'source-id',
      label: t('integration.zabbixSourceId'),
      value: guide.source_id ? String(guide.source_id) : '',
      display: guide.source_id ? String(guide.source_id) : '',
      copyable: true,
      masked: false,
    },
    {
      key: 'secret-header',
      label: t('integration.zabbixSecretHeader'),
      value: effectiveSecret,
      display: effectiveSecret ? secretMasked : secretPlaceholder,
      copyable: !!effectiveSecret,
      masked: true,
    },
  ].filter((item) => item.masked || item.value);

  return (
    <div className="space-y-4 px-[10px] py-4 max-h-[calc(100vh-330px)] overflow-y-auto">
      {credentialsSlot ? (
        <section className={sectionClassName}>
          <div className={sectionHeaderClassName}>
            <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
              {t('integration.credentialsAndExamples')}
            </div>
          </div>
          <div className={sectionBodyClassName}>
            {credentialsSlot}
          </div>
        </section>
      ) : null}

      {guide.description ? (
        <Alert
          type="info"
          showIcon
          className="rounded-[18px] border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_4%,var(--color-bg-1))]"
          message={t('integration.zabbixGuideOverview')}
          description={<span className="text-[13px] leading-6 text-[var(--color-text-2)]">{guide.description}</span>}
        />
      ) : null}

      {guide.key_reminders?.length ? (
        <section className={sectionClassName}>
          <div className={sectionHeaderClassName}>
            <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
              {t('integration.zabbixKeyReminders')}
            </div>
          </div>
          <div className={`${sectionBodyClassName} space-y-2`}>
            {guide.key_reminders.map((item, index) => (
              <div key={`${item}-${index}`} className="flex items-start gap-2 rounded-[14px] bg-[var(--color-fill-1)] px-3.5 py-3 text-[12px] leading-5 text-[var(--color-text-2)]">
                <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className={sectionClassName}>
        <div className={sectionHeaderClassName}>
          <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
            {t('integration.zabbixConnectionValues')}
          </div>
          <div className="mt-1 text-[12px] leading-5 text-[var(--color-text-3)]">
            {t('integration.zabbixConnectionValuesHelp')}
          </div>
        </div>
        <div className={sectionBodyClassName}>
          <Descriptions bordered size="small" column={1} labelStyle={{ width: 180, fontSize: 12, color: 'var(--color-text-3)' }}>
            {descriptionItems.map((item) => (
              <Descriptions.Item key={item.key} label={item.label}>
                <div className="flex min-w-0 items-center gap-2">
                  <span className={`min-w-0 flex-1 break-all font-mono text-[13px] leading-6 ${item.copyable ? 'text-[var(--color-text-1)]' : 'text-[var(--color-text-3)]'}`}>
                    {item.display}
                  </span>
                  {item.copyable ? (
                    <Button type="link" size="small" aria-label={t('common.copy')} icon={<CopyOutlined aria-hidden="true" />} onClick={() => copy(item.value || '')} />
                  ) : null}
                </div>
              </Descriptions.Item>
            ))}
            {Object.entries(guide.headers || {})
              .filter(([key]) => key !== 'SECRET')
              .map(([key, value]) => (
                <Descriptions.Item key={key} label={`${t('integration.headers')} · ${key}`}>
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="min-w-0 flex-1 break-all font-mono text-[13px] leading-6 text-[var(--color-text-1)]">
                      {String(value ?? '')}
                    </span>
                    <Button type="link" size="small" aria-label={t('common.copy')} icon={<CopyOutlined aria-hidden="true" />} onClick={() => copy(String(value || ''))} />
                  </div>
                </Descriptions.Item>
              ))}
          </Descriptions>
        </div>
      </section>

      <section className={sectionClassName}>
        <div className={sectionHeaderClassName}>
          <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
            {t('integration.zabbixParameterMapping')}
          </div>
          <div className="mt-1 text-[12px] leading-5 text-[var(--color-text-3)]">
            {t('integration.zabbixParameterMappingHelp')}
          </div>
        </div>
        <div className={sectionBodyClassName}>
          {parameterRows.length ? (
            <div className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]">
              <div className="grid grid-cols-[minmax(160px,220px)_minmax(0,1fr)] border-b border-[var(--color-border-1)] bg-[color-mix(in_srgb,var(--color-primary)_4%,var(--color-fill-1))]">
                <div className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                  {t('common.name')}
                </div>
                <div className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                  {t('common.value')}
                </div>
              </div>
              {parameterRows.map((item, index) => (
                <div
                  key={item.key}
                  className={`grid grid-cols-[minmax(160px,220px)_minmax(0,1fr)] ${index !== parameterRows.length - 1 ? 'border-b border-[var(--color-border-1)]' : ''}`}
                >
                  <div className="flex flex-col gap-1 px-4 py-3">
                    <span className="font-mono text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">{item.name}</span>
                    {item.required !== undefined ? (
                      <span className={`text-[11px] font-medium leading-4 ${item.required ? 'text-[var(--color-error)]' : 'text-[var(--color-text-3)]'}`}>
                        {item.required ? t('common.required') : t('integration.zabbixOptional')}
                      </span>
                    ) : null}
                  </div>
                  <div className="min-w-0 px-4 py-3">
                    <div className="flex min-w-0 items-start gap-2">
                      <span className={`min-w-0 flex-1 break-all font-mono text-[13px] leading-6 ${item.copyable ? 'text-[var(--color-text-1)]' : 'text-[var(--color-text-3)]'}`}>
                        {item.displayValue || '--'}
                      </span>
                      {item.copyable ? (
                        <Button type="link" size="small" aria-label={t('common.copy')} icon={<CopyOutlined aria-hidden="true" />} onClick={() => copy(item.value)} />
                      ) : null}
                    </div>
                    {item.description ? (
                      <div className="mt-1 text-[12px] leading-5 text-[var(--color-text-2)]">{item.description}</div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />}
        </div>
      </section>

      <section className={sectionClassName}>
        <div className={sectionHeaderClassName}>
          <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
            {t('integration.eventFieldsMapping')}
          </div>
        </div>
        <div className={`${sectionBodyClassName} space-y-3`}>
          {fieldMappings.length ? fieldMappings.map((item, index) => (
            <div key={`${item.bk_lite_field || 'field'}-${index}`} className={cardClassName}>
              <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                {t('integration.zabbixMapsTo')}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="font-mono text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">
                  {item.bk_lite_field || '--'}
                </span>
                <span className="text-[var(--color-text-3)]">←</span>
                <span className="text-[13px] leading-6 text-[var(--color-text-2)] break-all">
                  {item.upstream_source || item.zabbix_field || '--'}
                </span>
              </div>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />}
        </div>
      </section>

      <section className={sectionClassName}>
        <div className={sectionHeaderClassName}>
          <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
            {t('integration.zabbixScriptTemplate')}
          </div>
          <div className="mt-1 text-[12px] leading-5 text-[var(--color-text-3)]">
            {t('integration.zabbixScriptTemplateHelp')}
          </div>
        </div>
        <div className={sectionBodyClassName}>
          {guide.script_template ? (
            <div className={codeBlockClassName}>
              <pre className="overflow-x-auto pr-10 text-[13px] leading-6 text-[var(--color-text-1)] whitespace-pre-wrap break-all">
                <code>{applyEffectiveWebhookUrl(applyTeamSecret(guide.script_template))}</code>
              </pre>
              <CopyOutlined
                className={effectiveSecret ? copyIconClassName : `${copyIconClassName} cursor-not-allowed`}
                onClick={() => effectiveSecret && copy(applyEffectiveWebhookUrl(applyTeamSecret(guide.script_template)) || '')}
              />
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />
          )}
        </div>
      </section>

      <section className={sectionClassName}>
        <div className={sectionHeaderClassName}>
          <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
            {t('integration.deploySteps')}
          </div>
        </div>
        <div className={`${sectionBodyClassName} space-y-3`}>
          {setupSteps.length ? setupSteps.map((step, index) => (
            <div key={step.key} className={cardClassName}>
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-bg-active)] text-[12px] font-semibold text-[var(--color-primary)]">
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">{step.title}</div>
                  {step.items.length ? (
                    <ul className="mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
                      {step.items.map((item, itemIndex) => (
                        <li key={`${item}-${itemIndex}`} className="flex gap-2">
                          <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </div>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />}
        </div>
      </section>

      <section className={sectionClassName}>
        <div className={sectionHeaderClassName}>
          <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
            {t('integration.verifyResult')}
          </div>
        </div>
        <div className={`${sectionBodyClassName} grid gap-3 xl:grid-cols-3`}>
          {verificationCards.length ? verificationCards.map((item) => (
            <div key={item.key} className={cardClassName}>
              <div className="text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">{item.title}</div>
              <div className="mt-2">{renderCheckContent(item.check)}</div>
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />}
        </div>
      </section>

      <section className={sectionClassName}>
        <div className={sectionHeaderClassName}>
          <div className="text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
            {t('integration.zabbixTroubleshooting')}
          </div>
        </div>
        <div className={`${sectionBodyClassName} space-y-3`}>
          {troubleshootingItems.length ? troubleshootingItems.map((item) => (
            <div key={item.key} className={cardClassName}>
              <div className="text-[13px] font-semibold leading-6 text-[var(--color-text-1)]">{item.symptom || t('integration.zabbixCheckItem')}</div>
              {item.causes.length ? (
                <div className="mt-2">
                  <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]">
                    {t('integration.zabbixPossibleCauses')}
                  </div>
                  <ul className="mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
                    {item.causes.map((cause, index) => (
                      <li key={`${cause}-${index}`} className="flex gap-2">
                        <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-text-3)]" />
                        <span>{cause}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {item.resolutions.length ? (
                <div className="mt-3 rounded-[14px] border border-[color-mix(in_srgb,var(--color-primary)_14%,var(--color-bg-1))] bg-[color-mix(in_srgb,var(--color-primary)_6%,var(--color-bg-1))] px-3.5 py-3">
                  <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-primary)]">
                    {t('integration.zabbixResolutions')}
                  </div>
                  <ul className="mt-2 space-y-2 text-[12px] leading-5 text-[var(--color-text-2)]">
                    {item.resolutions.map((resolution, index) => (
                      <li key={`${resolution}-${index}`} className="flex gap-2">
                        <span className="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                        <span>{resolution}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />}
        </div>
      </section>
    </div>
  );
};

export default ZabbixGuide;
