'use client';

import React, { useState } from 'react';
import { Button } from 'antd';
import { CloseOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import { ChangeRecordScenarioTag } from './ChangeRecordScenarioTag';
import { SCENARIO_COLORS } from './changeRecordView';
import type { ChangeRecordRelationInfo } from './changeRecordView';
import type { ChangeRecord, ChangeRecordDiffRow } from './changeRecordTypes';
import TableFieldDiffView from './TableFieldDiffView';

function snapshotInstName(data?: Record<string, unknown>): string {
  const value = data?.inst_name;
  return typeof value === 'string' && value ? value : '';
}

export function ChangeRecordDetail({
  record,
  diffRows,
  relationInfo,
  scenarioLabel,
  showModelName,
  onClose,
  onPrev,
  onNext,
  canPrev = false,
  canNext = false,
}: {
  record: ChangeRecord | null;
  diffRows: ChangeRecordDiffRow[];
  relationInfo: ChangeRecordRelationInfo | null;
  scenarioLabel: (key: string) => string;
  showModelName: (id: string) => string;
  onClose?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  canPrev?: boolean;
  canNext?: boolean;
}) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<
    'summary' | 'attr_diff' | 'relation_diff'
  >('summary');

  if (!record) {
    return (
      <div className={styles.detailEmpty}>{t('Model.changeRecord.selectTip')}</div>
    );
  }

  const instName =
    snapshotInstName(record.after_data) || snapshotInstName(record.before_data);

  return (
    <>
      <div className={styles.detailHeader}>
        <div className={styles.detailHeaderRow}>
          <div className={styles.detailHeaderLeft}>
            <span
              className="h-2 w-2 rounded-full"
              style={{
                background: SCENARIO_COLORS[record.scenario]?.dot || '#155AEF',
              }}
            />
            <span className="whitespace-nowrap text-xs font-medium">
              {record.created_at}
            </span>
            <ChangeRecordScenarioTag
              scenario={record.scenario}
              label={scenarioLabel(record.scenario)}
            />
            <span className="text-xs text-[var(--color-text-3)]">
              {record.operator}
            </span>
          </div>
          {(onPrev || onNext || onClose) ? (
            <div className="flex items-center gap-1">
              {onPrev ? (
                <Button
                  size="small"
                  disabled={!canPrev}
                  icon={<LeftOutlined />}
                  onClick={onPrev}
                />
              ) : null}
              {onNext ? (
                <Button
                  size="small"
                  disabled={!canNext}
                  icon={<RightOutlined />}
                  onClick={onNext}
                />
              ) : null}
              {onClose ? (
                <Button size="small" icon={<CloseOutlined />} onClick={onClose} />
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className={styles.detailTabs}>
        {(
          [
            ['summary', t('Model.changeRecord.summary')],
            ['attr_diff', t('Model.changeRecord.attrCompare')],
            ['relation_diff', t('Model.changeRecord.relationCompare')],
          ] as const
        ).map(([key, label]) => (
          <div
            key={key}
            className={`${styles.detailTab} ${
              activeTab === key ? styles.tabActive : ''
            }`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </div>
        ))}
      </div>

      <div className={styles.detailBody}>
        {activeTab === 'summary' && (
          <>
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <span className={styles.sectionBar} />
                {t('Model.baseInfo')}
              </div>
              <div className={styles.infoGrid}>
                <span className={styles.infoLabel}>
                  {t('Model.changeRecord.changeObject')}
                </span>
                <span className={styles.infoValue}>
                  {record.model_object || showModelName(record.model_id)}
                  {instName ? ` / ${instName}` : ''}
                </span>
                <span className={styles.infoLabel}>
                  {t('Model.changeRecord.changeType')}
                </span>
                <span className={styles.infoValue}>
                  {scenarioLabel(record.scenario)}
                </span>
                <span className={styles.infoLabel}>
                  {t('Model.changeRecord.operatorLabel')}
                </span>
                <span className={styles.infoValue}>{record.operator}</span>
                <span className={styles.infoLabel}>
                  {t('Model.changeRecord.changeTime')}
                </span>
                <span className={styles.infoValue}>{record.created_at}</span>
                {record.message ? (
                  <>
                    <span className={styles.infoLabel}>
                      {t('Model.changeRecord.message')}
                    </span>
                    <span className={styles.infoValue}>{record.message}</span>
                  </>
                ) : null}
              </div>
            </div>

            {record.label === 'instance' && diffRows.length > 0 ? (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <span className={styles.sectionBar} />
                  {t('Model.changeRecord.changeSummary')}
                </div>
                <div className="overflow-x-auto">
                  <table className={styles.diffTable}>
                    <thead>
                      <tr>
                        <th className="w-[22%]" />
                        <th>{t('Model.beforeTheChange')}</th>
                        <th>{t('Model.afterTheChange')}</th>
                        <th>{t('Model.changeRecord.current')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diffRows.map((row) =>
                        row.table ? (
                          <tr key={row.attrId}>
                            <td className={styles.attrCell}>{row.attr}</td>
                            <td colSpan={3} className="p-2">
                              <TableFieldDiffView diff={row.table} compact />
                            </td>
                          </tr>
                        ) : (
                          <tr key={row.attrId}>
                            <td className={styles.attrCell}>{row.attr}</td>
                            <td className="whitespace-pre-wrap break-words text-[var(--color-text-1)]">
                              {row.before}
                            </td>
                            <td>
                              <span
                                className={`whitespace-pre-wrap break-words ${
                                  row.changed
                                    ? 'text-[#12B76A]'
                                    : 'text-[var(--color-text-1)]'
                                }`}
                              >
                                {row.after}
                              </span>
                            </td>
                            <td>
                              <span
                                className={`whitespace-pre-wrap break-words ${
                                  row.currentDiff
                                    ? 'font-medium text-[#F79009]'
                                    : 'font-normal text-[var(--color-text-1)]'
                                }`}
                              >
                                {row.current}
                              </span>
                            </td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            {relationInfo ? (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <span className={styles.sectionBar} />
                  {t('Model.changeRecord.relationSummary')}
                </div>
                <div className={styles.relationBox}>
                  <span
                    className={`font-semibold ${
                      relationInfo.kind === 'add'
                        ? 'text-[#12B76A]'
                        : 'text-[#F04438]'
                    }`}
                  >
                    {relationInfo.kind === 'add' ? '+' : '−'}
                  </span>
                  <span className="font-medium">
                    {relationInfo.kind === 'add'
                      ? t('Model.changeRecord.addRelation')
                      : t('Model.changeRecord.removeRelation')}
                    ：
                  </span>
                  <span className="text-[var(--color-primary)]">
                    {relationInfo.dst}
                  </span>
                </div>
              </div>
            ) : null}

            {diffRows.length === 0 && !relationInfo ? (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>
                  <span className={styles.sectionBar} />
                  {t('Model.changeRecord.changeSummary')}
                </div>
                <div className={styles.emptyTip}>
                  {t('Model.changeRecord.noChangeContent')}
                </div>
              </div>
            ) : null}
          </>
        )}

        {activeTab === 'attr_diff' && (
          <>
            <div className={styles.sectionTitle}>
              <span className={styles.sectionBar} />
              {t('Model.changeRecord.attrCompare')}
            </div>
            {diffRows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className={styles.diffTable}>
                  <thead>
                    <tr>
                      <th className="w-[22%]">{t('Model.attribute')}</th>
                      <th>{t('Model.beforeTheChange')}</th>
                      <th>{t('Model.afterTheChange')}</th>
                      <th>{t('Model.changeRecord.current')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diffRows.map((row) =>
                      row.table ? (
                        <tr key={row.attrId}>
                          <td className={styles.attrCell}>{row.attr}</td>
                          <td colSpan={3} className="p-2">
                            <TableFieldDiffView diff={row.table} />
                          </td>
                        </tr>
                      ) : (
                        <tr key={row.attrId}>
                          <td className={styles.attrCell}>{row.attr}</td>
                          <td
                            className={`whitespace-pre-wrap break-words ${
                              row.changed
                                ? 'text-[#F04438] line-through opacity-60'
                                : 'text-[var(--color-text-1)]'
                            }`}
                          >
                            {row.before}
                          </td>
                          <td
                            className={`whitespace-pre-wrap break-words ${
                              row.changed
                                ? 'font-medium text-[#12B76A]'
                                : 'font-normal text-[var(--color-text-1)]'
                            }`}
                          >
                            {row.after}
                          </td>
                          <td
                            className={`whitespace-pre-wrap break-words ${
                              row.currentDiff
                                ? 'font-medium text-[#F79009]'
                                : 'font-normal text-[var(--color-text-1)]'
                            }`}
                          >
                            {row.current}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className={styles.emptyTip}>
                {t('Model.changeRecord.noAttrDiff')}
              </div>
            )}
          </>
        )}

        {activeTab === 'relation_diff' && (
          <>
            <div className={styles.sectionTitle}>
              <span className={styles.sectionBar} />
              {t('Model.changeRecord.relationCompare')}
            </div>
            {relationInfo ? (
              <div className={styles.relationBox}>
                <div>
                  <div className="mb-2 flex items-center gap-2">
                    <span
                      className={`font-semibold ${
                        relationInfo.kind === 'add'
                          ? 'text-[#12B76A]'
                          : 'text-[#F04438]'
                      }`}
                    >
                      {relationInfo.kind === 'add' ? '+' : '−'}
                    </span>
                    <span>
                      {relationInfo.kind === 'add'
                        ? t('Model.changeRecord.addRelation')
                        : t('Model.changeRecord.removeRelation')}
                    </span>
                  </div>
                  <div className="ml-5 text-[var(--color-text-2)]">
                    {relationInfo.src} → {relationInfo.dst}
                  </div>
                </div>
              </div>
            ) : (
              <div className={styles.emptyTip}>
                {t('Model.changeRecord.noRelationDiff')}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
