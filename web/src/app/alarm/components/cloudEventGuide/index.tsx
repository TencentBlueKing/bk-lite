'use client';

import React from 'react';
import { Alert, Descriptions, Empty, Table } from 'antd';
import { useTranslation } from '@/utils/i18n';
import ExampleCopyBlock from '@/app/alarm/components/exampleCopyBlock';
import {
  AlertSourceIntegrationGuide,
  IntegrationGuideStepItem,
} from '@/app/alarm/types/integration';

interface CloudEventGuideProps {
  guide?: AlertSourceIntegrationGuide;
  credentialsSlot?: React.ReactNode;
  selectedTeamSecret?: string;
}

const headingClassName = 'mb-3 font-medium pl-2 border-l-2 border-[var(--color-primary)] leading-tight';
const proseClassName = 'mb-2 text-[13px] leading-6 text-[var(--color-text-1)]';

const LEVEL_NAME: Record<string, string> = {
  '0': '严重',
  '1': '错误',
  '2': '警告',
  '3': '提醒',
};

export function isCloudEventGuideSource(sourceId?: string) {
  return sourceId === 'aliyun_eventbridge' || sourceId === 'tencent_eventbus';
}

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '0.0.0.0', '::1']);

function withSelectedSecret(raw: string | undefined, secret?: string) {
  if (!raw) return '';
  if (!secret) return raw;
  return raw.split('{{TEAM_SECRET}}').join(secret);
}

function browserOrigin() {
  if (typeof window === 'undefined') return '';
  if (LOOPBACK_HOSTS.has(window.location.hostname)) return '';
  return window.location.origin.replace(/\/$/, '');
}

function presentCallbackText(raw: string | undefined, sourceId?: string) {
  const path = sourceId ? `/api/v1/alerts/api/source/${sourceId}/webhook/` : '';
  let text = raw || (path ? `{url}${path}` : '');
  text = text.replace(/https?:\/\/(127\.0\.0\.1|localhost|0\.0\.0\.0)(:\d+)?/g, '{url}');
  const origin = browserOrigin();
  if (origin) {
    text = text.split('{url}').join(origin);
  }
  return text;
}

function stepText(step: string | IntegrationGuideStepItem) {
  if (typeof step === 'string') return step;
  return step.title || step.description || step.content || '';
}

const CloudEventGuide = ({ guide, credentialsSlot, selectedTeamSecret }: CloudEventGuideProps) => {
  const { t } = useTranslation();
  if (!guide) {
    return <Empty />;
  }

  const ready = Boolean(selectedTeamSecret);
  const secret = ready ? selectedTeamSecret : undefined;
  const sourceId = guide.source_id;
  const showText = (raw?: string) => withSelectedSecret(presentCallbackText(raw, sourceId), secret);
  const queryUrl = showText(guide.webhook_url_with_secret);
  const callbackUrl = showText(guide.webhook_url);
  const examples = guide.example_items?.length
    ? guide.example_items
    : (guide.examples?.CURL
      ? [{ title: 'CURL', explain: guide.description || '', lands: [], curl: guide.examples.CURL }]
      : []);
  const python = showText(guide.examples?.Python);
  const base = guide.base_info;
  const mapping = guide.field_mapping || [];

  return (
    <div className="flex max-h-[calc(100vh-330px)] flex-col gap-4 overflow-y-auto">
      {credentialsSlot}
      {ready ? null : (
        <Alert type="info" showIcon message={t('integration.cloudGuideSelectSecretHint')} />
      )}

      <section>
        <h4 className={headingClassName}>{t('integration.baseInfo')}</h4>
        {callbackUrl.includes('{url}') ? (
          <p className={proseClassName}>{t('integration.cloudGuideUrlNote')}</p>
        ) : null}
        <Descriptions bordered size="small" column={1} styles={{ label: { width: 120 } }}>
          <Descriptions.Item label="ID">{base?.id || sourceId}</Descriptions.Item>
          <Descriptions.Item label="url">{base?.url || `/api/v1/alerts/api/source/${sourceId}/webhook/`}</Descriptions.Item>
          <Descriptions.Item label="method">{base?.method || 'POST'}</Descriptions.Item>
          <Descriptions.Item label="headers">
            {showText(JSON.stringify(base?.headers || { SECRET: '{{TEAM_SECRET}}' }))}
          </Descriptions.Item>
          <Descriptions.Item label="params">{JSON.stringify(base?.params || {})}</Descriptions.Item>
          <Descriptions.Item label="content_type">{base?.content_type || 'application/json'}</Descriptions.Item>
          <Descriptions.Item label="description">{base?.description || guide.description}</Descriptions.Item>
        </Descriptions>
        <div className="mt-3">
          <ExampleCopyBlock text={callbackUrl} enabled={Boolean(callbackUrl) && !callbackUrl.includes('{url}')} />
        </div>
        {guide.webhook_url_with_secret ? (
          <div className="mt-3">
            <p className="mb-2 text-[13px] leading-6 text-[var(--color-text-2)]">
              {t('integration.cloudGuideQueryUrl')}
            </p>
            <ExampleCopyBlock text={queryUrl} enabled={ready && Boolean(queryUrl) && !queryUrl.includes('{url}')} />
          </div>
        ) : null}
      </section>

      {(guide.sections || []).map((section) => (
        <section key={section.title}>
          <h4 className={headingClassName}>{section.title}</h4>
          {section.paragraphs.map((paragraph) => (
            <p key={paragraph} className={proseClassName}>{paragraph}</p>
          ))}
        </section>
      ))}

      {guide.sections?.length ? null : (
        <section>
          <h4 className={headingClassName}>{t('integration.cloudGuideSteps')}</h4>
          <ol className="list-decimal space-y-2 pl-5 text-[13px] leading-6 text-[var(--color-text-1)]">
            {(guide.steps || []).map((step, index) => (
              <li key={`${index}-${stepText(step)}`}>{stepText(step)}</li>
            ))}
          </ol>
        </section>
      )}

      <section>
        <h4 className={headingClassName}>{t('integration.eventFieldsMapping')}</h4>
        {guide.field_mapping_note ? (
          <p className={proseClassName}>{guide.field_mapping_note}</p>
        ) : null}
        <Descriptions bordered size="small" column={1} styles={{ label: { width: 148 } }}>
          {mapping.map((row) => (
            <Descriptions.Item key={row.field} label={row.field}>
              {row.from}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </section>

      <section>
        <h4 className={headingClassName}>{t('integration.eventFieldsDescription')}</h4>
        <Descriptions bordered size="small" column={1} styles={{ label: { width: 148 } }}>
          {mapping.map((row) => (
            <Descriptions.Item key={row.field} label={row.field}>
              {row.detail}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </section>

      <section>
        <h4 className={headingClassName}>{t('integration.exampleRequests')}</h4>
        {guide.description ? <p className={proseClassName}>{guide.description}</p> : null}
        {examples.map((item) => (
          <div key={item.title} className="mb-4">
            <h5 className="mb-2 text-[14px] font-medium text-[var(--color-text-1)]">{item.title}</h5>
            {item.explain ? <p className={proseClassName}>{item.explain}</p> : null}
            {item.lands?.length ? (
              <>
                <div className="mb-2 text-[13px] text-[var(--color-text-3)]">{t('integration.cloudGuideLands')}</div>
                <pre className="mb-3 whitespace-pre-wrap break-all rounded border border-[var(--color-border-1)] bg-[var(--color-bg-5)] p-3 text-[13px] leading-relaxed text-[var(--color-text-1)]">
                  {item.lands.join('\n')}
                </pre>
              </>
            ) : null}
            <ExampleCopyBlock text={showText(item.curl)} enabled={ready && Boolean(item.curl)} />
          </div>
        ))}
        {python ? (
          <div>
            <div className="mb-2 text-[13px] text-[var(--color-text-3)]">Python</div>
            <ExampleCopyBlock text={python} enabled={ready && Boolean(python)} />
          </div>
        ) : null}
      </section>

      <section>
        <h4 className={headingClassName}>{t('integration.cloudGuideCatalog')}</h4>
        {guide.catalog_text ? (
          <pre className="mb-3 whitespace-pre-wrap break-all rounded border border-[var(--color-border-1)] bg-[var(--color-bg-5)] p-3 text-[13px] leading-relaxed text-[var(--color-text-1)]">
            {guide.catalog_text}
          </pre>
        ) : null}
        <Table
          size="small"
          pagination={false}
          rowKey="event"
          dataSource={guide.report_fields || []}
          columns={[
            { title: '事件名', dataIndex: 'event' },
            { title: '中文名', dataIndex: 'title' },
            {
              title: '级别',
              dataIndex: 'level',
              render: (level: string) => `${level} ${LEVEL_NAME[level] || ''}`.trim(),
            },
            { title: '资源', dataIndex: 'resource' },
            {
              title: '告警',
              dataIndex: 'stateless',
              render: (stateless: boolean) => (stateless ? '只记事件' : '可建告警'),
            },
          ]}
        />
      </section>

      {guide.key_reminders?.length ? (
        <Alert
          type="warning"
          showIcon
          message={t('integration.cloudGuideReminders')}
          description={(
            <ul className="mb-0 list-disc pl-4">
              {guide.key_reminders.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        />
      ) : null}
    </div>
  );
};

export default CloudEventGuide;
