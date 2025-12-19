'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Tabs, Swiper, ErrorBlock, SpinLoading } from 'antd-mobile';
import { SearchOutline, LeftOutline } from 'antd-mobile-icons';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { useTranslation } from '@/utils/i18n';
import { getApplication } from '@/api/bot';
import { getAvatar } from '@/utils/avatar';

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
    const [botList, setBotList] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const swiperRef = useRef<any>(null);

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
    const fetchApplications = useCallback(async (tabKey: TabKey, params?: any) => {
        // 取消上一个请求
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        // 创建新的 AbortController
        const controller = new AbortController();
        abortControllerRef.current = controller;

        setLoading(true);

        try {
            const requestParams: any = {
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
                setBotList([]);
                return;
            }
            setBotList(response?.data.items || []);
        } catch (error: any) {
            // 忽略取消的请求错误
            if (error?.name === 'AbortError') {
                return;
            }
            console.error('Failed to fetch applications:', error);
            setBotList([]);
        } finally {
            // 只在非取消情况下更新 loading 状态
            if (!controller.signal.aborted) {
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

    // 当 activeTab 改变时，同步 Swiper
    useEffect(() => {
        const index = tabItems.findIndex((item) => item.key === activeTab);
        if (index !== -1 && swiperRef.current) {
            swiperRef.current.swipeTo(index);
        }
    }, [activeTab]);

    // app_tags 映射
    const appTagsMap: { [key: string]: string } = {
        'routine_ops': t('workbench.routineOps'),
        'monitor_alarm': t('workbench.monitorAlarm'),
        'automation': t('workbench.automation'),
        'security_audit': t('workbench.securityAudit'),
        'performance_analysis': t('workbench.performanceAnalysis'),
        'ops_plan': t('workbench.opsPlan'),
    };

    const appTagColors: { [key: string]: { bg: string; text: string } } = {
        'routine_ops': { bg: '#E5F4FF', text: '#4A9EFF' },
        'monitor_alarm': { bg: '#FFE5E5', text: '#FF6B9D' },
        'automation': { bg: '#FFF4E5', text: '#FFB84D' },
        'security_audit': { bg: '#E5FFE5', text: '#52C41A' },
        'performance_analysis': { bg: '#F0E5FF', text: '#9B59B6' },
        'ops_plan': { bg: '#E5F0FF', text: '#3498DB' },
    };

    const handleTabChange = (key: string) => {
        setActiveTab(key as TabKey);
    };

    // 渲染列表项
    const renderListItem = (item: any) => (
        <div
            key={item.id}
            className="bg-[var(--color-bg)] mx-3 mt-3 rounded-lg shadow-sm border border-[var(--color-border)] p-4 active:bg-[var(--color-bg-hover)] cursor-pointer relative overflow-hidden"
            onClick={() => {
                router.push(`/workbench/detail?bot_id=${item.bot}`);
            }}
        >
            {/* 右上角状态 - 默认在线 */}
            <div
                className="absolute top-0 right-0 w-6 h-6"
                style={{
                    clipPath: 'polygon(100% 0, 100% 100%, 0 0)',
                    backgroundColor: '#52C41A',
                }}
            ></div>

            <div className="flex items-start space-x-3">
                {/* 缩略图 */}
                <div className="flex-shrink-0 relative">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full overflow-hidden">
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
                            {item.app_tags.map((tag: string) => (
                                <span
                                    key={tag}
                                    className="px-2 py-0.5 text-xs font-medium rounded"
                                    style={{
                                        backgroundColor: appTagColors[tag]?.bg || '#F0F0F0',
                                        color: appTagColors[tag]?.text || '#666666',
                                    }}
                                >
                                    {appTagsMap[tag] || tag}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
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
        <div className="h-full flex flex-col items-center justify-center">
            <SpinLoading color="primary" />
        </div>
    );

    // 渲染内容
    const renderContent = () => {
        if (loading) {
            return renderLoading();
        }
        if (botList.length > 0) {
            return botList.map((item) => renderListItem(item));
        }
        return renderEmptyState();
    };

    return (
        <div className="flex flex-col h-screen bg-[var(--color-background-body)]">
            {/* 标签栏和搜索图标 */}
            <div className="bg-[var(--color-bg)] flex items-center">
                <div className="pl-2 py-3 flex-shrink-0 ">
                    <LeftOutline
                        className="text-2xl text-[var(--color-text-2)]"
                        onClick={() => router.back()}
                    />
                </div>
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
                <div className="pl-1 pr-2 py-3 flex-shrink-0 ">
                    <SearchOutline
                        className="text-2xl text-[var(--color-text-2)]"
                        onClick={() => router.push('/search?type=WorkbenchPage')}
                    />
                </div>
            </div>

            {/* Swiper 滑动切换 */}
            <Swiper
                direction="horizontal"
                loop={false}
                indicator={() => null}
                ref={swiperRef}
                defaultIndex={0}
                onIndexChange={(index) => {
                    const key = tabItems[index].key;
                    setActiveTab(key);
                }}
                style={{ flex: 1 }}
            >
                {tabItems.map((tab) => {
                    return (
                        <Swiper.Item key={tab.key}>
                            <div className="h-full overflow-auto pb-20">
                                {renderContent()}
                            </div>
                        </Swiper.Item>
                    );
                })}
            </Swiper>
        </div>
    );
}