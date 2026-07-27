'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Tabs, ErrorBlock, SpinLoading } from 'antd-mobile';
import { MessageOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { useTranslation } from '@/utils/i18n';
import {
    ChatApplicationItem,
    GetApplicationsParams,
    getApplication,
    getApplicationItems,
} from '@/api/bot';
import { getAvatar } from '@/utils/avatar';
import { getAppTagColor, getAppTagLabel } from '@/constants/workbenchTags';
import MobileTabShell from '@/components/mobile-tab-shell';
import MobilePageHeader from '@/components/mobile-page-header';
import MobilePullToRefresh from '@/components/mobile-pull-to-refresh';
import { buildConversationHref } from '@/utils/conversationRoute';

type TabKey =
    | 'all'
    | 'routine_ops'
    | 'monitor_alarm'
    | 'automation'
    | 'security_audit'
    | 'performance_analysis'
    | 'ops_plan';

export default function WorkbenchPage() {
    const { t } = useTranslation();
    const router = useRouter();
    const [activeTab, setActiveTab] = useState<TabKey>('all');
    const [botList, setBotList] = useState<ChatApplicationItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [loadFailed, setLoadFailed] = useState(false);

    // 用于取消请求的 AbortController
    const abortControllerRef = useRef<AbortController | null>(null);

    // Tab 配置项，使用多语言
    const tabItems = [
        { key: 'all' as TabKey, title: t('workbench.all') },
        { key: 'routine_ops' as TabKey, title: t('workbench.routineOps') },
        { key: 'monitor_alarm' as TabKey, title: t('workbench.monitorAlarm') },
        { key: 'automation' as TabKey, title: t('workbench.automation') },
        { key: 'security_audit' as TabKey, title: t('workbench.securityAudit') },
        { key: 'performance_analysis' as TabKey, title: t('workbench.performanceAnalysis') },
        { key: 'ops_plan' as TabKey, title: t('workbench.opsPlan') },
    ];

    // 获取应用列表
    const fetchApplications = useCallback(async (
        tabKey: TabKey,
        options: Pick<GetApplicationsParams, 'page' | 'page_size'> & { preserveContent?: boolean } = {},
    ) => {
        const { preserveContent = false, ...params } = options;
        // 取消上一个请求
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        // 创建新的 AbortController
        const controller = new AbortController();
        abortControllerRef.current = controller;

        if (!preserveContent) {
            setLoading(true);
            setLoadFailed(false);
        }

        try {
            const requestParams: GetApplicationsParams = {
                page: params?.page || 1,
                page_size: params?.page_size || 20,
            };

            // 如果不是 'all'，添加 app_tags 过滤
            if (tabKey !== 'all') {
                requestParams.app_tags = tabKey;
            }

            const response = await getApplication(requestParams, { signal: controller.signal });

            // 检查请求是否被取消
            if (controller.signal.aborted) {
                return;
            }
            if (!response.result) {
                throw new Error(response.message || 'Failed to fetch applications');
            }
            setBotList(getApplicationItems(response));
            setLoadFailed(false);
        } catch (error: unknown) {
            // 忽略取消的请求错误
            if (error instanceof DOMException && error.name === 'AbortError') {
                return;
            }
            console.error('Failed to fetch applications:', error);
            if (preserveContent) {
                throw error;
            }
            setBotList([]);
            setLoadFailed(true);
        } finally {
            // 只在非取消情况下更新 loading 状态
            if (!preserveContent && !controller.signal.aborted) {
                setLoading(false);
            }
        }
    }, []);

    // 初始加载和 tab 切换时请求数据
    useEffect(() => {
        fetchApplications(activeTab);

        // 组件卸载时取消请求
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, [activeTab, fetchApplications]);

    const handleTabChange = (key: string) => {
        setActiveTab(key as TabKey);
    };

    // 渲染列表项
    const renderListItem = (item: ChatApplicationItem) => (
        <button
            type="button"
            key={item.id}
            className="block w-[calc(100%_-_1.5rem)] bg-[var(--color-bg)] mx-3 mt-3 rounded-lg shadow-sm border border-[var(--color-border)] p-4 text-left active:bg-[var(--color-bg-hover)] cursor-pointer relative overflow-hidden"
            onClick={() => {
                router.push(buildConversationHref({ botId: item.bot, nodeId: item.node_id }));
            }}
        >
            {/* 右上角状态 - 默认在线 */}
            <div
                className="absolute top-0 right-0 w-6 h-6"
                style={{
                    clipPath: 'polygon(100% 0, 100% 100%, 0 0)',
                    backgroundColor: 'var(--color-success)',
                }}
            ></div>

            <div className="flex items-start space-x-3">
                {/* 缩略图 */}
                <div className="flex-shrink-0 relative">
                    <div className="w-16 h-16 bg-[var(--color-fill-2)] rounded-full overflow-hidden">
                        <Image
                            src={getAvatar(item.id)}
                            alt={item.app_name}
                            width={64}
                            height={64}
                            className="w-full h-full object-cover"
                        />
                    </div>
                </div>

                {/* 内容区域 */}
                <div className="flex-1 min-w-0">
                    {/* 名称 */}
                    <div className="flex items-center justify-between mb-1.5">
                        <h3 className="text-base font-medium text-[var(--color-text-1)]">
                            {item.app_name}
                        </h3>
                    </div>

                    {/* 描述文本 */}
                    <p className="text-xs text-[var(--color-text-2)] mb-3 leading-relaxed truncate">
                        {item.app_description || t('workbench.noIntroduction')}
                    </p>

                    {/* 标签按钮 */}
                    {item.app_tags && item.app_tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 justify-end">
                            {item.app_tags.map((tag: string) => {
                                const tagColor = getAppTagColor(tag);
                                return (
                                    <span
                                        key={tag}
                                        className="px-2 py-0.5 text-xs font-medium rounded"
                                        style={{
                                            backgroundColor: tagColor.bg,
                                            color: tagColor.text,
                                        }}
                                    >
                                        {getAppTagLabel(tag, t)}
                                    </span>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        </button>
    );

    // 渲染空状态
    const renderEmptyState = () => (
        <div className="h-full flex flex-col items-center justify-center">
            <div dangerouslySetInnerHTML={{
                __html: `
                <style>
                  .adm-error-block-image svg { width: 100% !important;}
                </style>
            ` }} />
            <ErrorBlock status="empty" />
        </div>
    );

    // 渲染加载状态
    const renderLoading = () => (
        <div className="flex min-h-32 items-center justify-center">
            <SpinLoading color="primary" />
        </div>
    );

    const renderLoadFailed = () => (
        <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <ErrorBlock
                status="disconnected"
                title={t('workbench.loadFailed')}
                description={t('workbench.loadFailedDescription')}
            >
                <button
                    type="button"
                    className="min-h-11 rounded-lg px-4 text-[var(--color-primary)] active:bg-[var(--color-fill-2)]"
                    onClick={() => void fetchApplications(activeTab)}
                >
                    {t('common.retry')}
                </button>
            </ErrorBlock>
        </div>
    );

    // 渲染内容
    const renderContent = () => {
        if (loading) {
            return renderLoading();
        }
        if (loadFailed) {
            return renderLoadFailed();
        }
        if (botList.length > 0) {
            return botList.map((item) => renderListItem(item));
        }
        return renderEmptyState();
    };

    return (
        <MobileTabShell activeTab="apps">
        <div className="flex flex-col h-full bg-[var(--color-background-body)]">
            <MobilePageHeader
                title={t('navigation.apps')}
                searchType="WorkbenchPage"
                actions={[{
                    href: '/conversations',
                    icon: <MessageOutline aria-hidden="true" />,
                    label: t('navigation.conversations'),
                }]}
            />

            {/* 应用分类 */}
            <div className="bg-[var(--color-bg)] flex items-center border-b border-[var(--color-border-1)]">
                <div className="flex-1 overflow-hidden">
                    <style dangerouslySetInnerHTML={{
                        __html: `
                            .adm-tabs-header {
                                color: var(--color-text-1) !important;
                                border-bottom: none !important;
                            }
                            .adm-tabs-tab-list {
                                overflow-x: auto !important;
                                -webkit-overflow-scrolling: touch;
                                scrollbar-width: none;
                            }
                            .adm-tabs-tab-list::-webkit-scrollbar {
                                display: none;
                            }
                        `
                    }} />
                    <Tabs
                        activeKey={activeTab}
                        onChange={handleTabChange}
                        style={{
                            '--title-font-size': '16px',
                            '--content-padding': '0',
                        }}
                    >
                        {tabItems.map((item) => (
                            <Tabs.Tab title={item.title} key={item.key} />
                        ))}
                    </Tabs>
                </div>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto pb-4">
                <MobilePullToRefresh
                    onRefresh={() => fetchApplications(activeTab, { preserveContent: true })}
                >
                    <div className="min-h-full">
                        {renderContent()}
                    </div>
                </MobilePullToRefresh>
            </div>
        </div>
        </MobileTabShell>
    );
}
