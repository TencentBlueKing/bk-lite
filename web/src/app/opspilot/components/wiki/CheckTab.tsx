'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Drawer, Empty, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { CheckItem } from '@/app/opspilot/types/wiki';

const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
const mdHtml = (body: string) => ({ __html: DOMPurify.sanitize(md.render(body || '')) });
const MD_CLS =
  'text-sm leading-7 break-words [&_h1]:text-base [&_h2]:text-[15px] [&_h3]:text-sm [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[var(--color-fill-1)] [&_code]:px-1';

const STATUS_COLOR: Record<string, string> = {
  open: 'gold',
  resolved: 'green',
  dismissed: 'default',
};

// 检查类型本地化(spec 4.5)
const CHECK_TYPE_KEY: Record<string, string> = {
  conflict: 'wiki.checkConflict',
  duplicate: 'wiki.checkDuplicate',
  stale: 'wiki.checkStale',
  orphan: 'wiki.checkOrphan',
  broken_relation: 'wiki.checkBrokenRelation',
  no_source: 'wiki.checkNoSource',
  all_sources_invalid: 'wiki.checkAllSourcesInvalid',
  low_confidence: 'wiki.checkLowConfidence',
  cannot_merge: 'wiki.checkCannotMerge',
  schema_violation: 'wiki.checkSchemaViolation',
  missing: 'wiki.checkMissing',
  material_update: 'wiki.checkMaterialUpdate',
  source_invalid: 'wiki.checkSourceInvalid',
};

const CheckTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchCheckItems, acceptCheck, rejectCheck, scan } = useWikiApi();
  const [data, setData] = useState<CheckItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [detail, setDetail] = useState<CheckItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchCheckItems(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await scan(kbId);
      message.success(t('wiki.saveSuccess'));
      load();
    } finally {
      setScanning(false);
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    await fn();
    message.success(t('wiki.saveSuccess'));
    setDetail(null);
    load();
  };

  const typeLabel = (ct: string) => (CHECK_TYPE_KEY[ct] ? t(CHECK_TYPE_KEY[ct]) : ct);

  const columns: ColumnsType<CheckItem> = [
    {
      title: t('wiki.type'),
      dataIndex: 'check_type',
      key: 'check_type',
      width: 160,
      render: (ct: string) => typeLabel(ct),
    },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    {
      title: t('wiki.related'),
      key: 'related',
      render: (_: unknown, r) => {
        const pages = r.related_pages || [];
        if (!pages.length) return <span className="text-xs text-[var(--color-text-3)]">--</span>;
        // 列出涉及页面标题(同标题重复时会一致),点「详情」看实际内容/对比
        return <span className="text-[var(--color-text-2)]">{pages.map((p) => p.title).join('  ·  ')}</span>;
      },
    },
    {
      title: '',
      key: 'action',
      width: 200,
      render: (_: unknown, r) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => setDetail(r)}>
            {t('wiki.detail')}
          </Button>
          {r.status === 'open' &&
            (r.candidate_version ? (
              // 候选类(资料更新等):可采纳候选版本或丢弃
              <>
                <Button type="link" size="small" onClick={() => act(() => acceptCheck(r.id))}>
                  {t('wiki.accept')}
                </Button>
                <Button type="link" size="small" danger onClick={() => act(() => rejectCheck(r.id))}>
                  {t('wiki.reject')}
                </Button>
              </>
            ) : (
              // 扫描类(重复/低置信等):无候选版本,仅能忽略(标记已处理)
              <Button type="link" size="small" onClick={() => act(() => rejectCheck(r.id))}>
                {t('wiki.dismiss')}
              </Button>
            ))}
        </Space>
      ),
    },
  ];

  const pages = detail?.related_pages || [];

  return (
    <div>
      <div className="flex justify-end mb-3">
        <Button onClick={handleScan} loading={scanning}>
          {t('wiki.scan')}
        </Button>
      </div>
      <CustomTable<CheckItem>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ x: undefined }}
      />

      {/* 检查详情:候选类展示「当前 vs 候选」对比,扫描类展示涉及页面内容 */}
      <Drawer
        title={detail ? typeLabel(detail.check_type) : ''}
        open={!!detail}
        width={760}
        onClose={() => setDetail(null)}
        destroyOnHidden
      >
        {detail &&
          (detail.candidate ? (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="mb-2 text-xs font-medium text-[var(--color-text-3)]">{t('wiki.currentVersion')}</div>
                <div className={MD_CLS} dangerouslySetInnerHTML={mdHtml(pages[0]?.body || '')} />
              </div>
              <div className="border-l border-[var(--color-border-2)] pl-4">
                <div className="mb-2 text-xs font-medium text-[var(--color-primary)]">{t('wiki.candidateVersion')}</div>
                <div className={MD_CLS} dangerouslySetInnerHTML={mdHtml(detail.candidate.body)} />
              </div>
            </div>
          ) : pages.length ? (
            <div className="space-y-4">
              <div className="text-xs text-[var(--color-text-3)]">{t('wiki.involvedPages')}</div>
              {pages.map((p) => (
                <div key={p.id} className="rounded-lg border border-[var(--color-border-2)] p-3">
                  <div className="mb-2 flex items-center gap-2 font-medium text-[var(--color-text-1)]">
                    {p.title}
                    <Tag className="m-0">{p.page_type}</Tag>
                  </div>
                  {p.body ? (
                    <div className={MD_CLS} dangerouslySetInnerHTML={mdHtml(p.body)} />
                  ) : (
                    <span className="text-xs text-[var(--color-text-3)]">--</span>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <Empty />
          ))}
      </Drawer>
    </div>
  );
};

export default CheckTab;
