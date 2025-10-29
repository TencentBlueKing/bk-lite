'use client';

import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Tabs, Swiper, ErrorBlock } from 'antd-mobile';
import { SearchOutline } from 'antd-mobile-icons';
import { useTranslation } from '@/utils/i18n';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import BottomTabBar from '@/components/bottom-tab-bar';
import { mockWorkbenchData } from '@/constants/mockData';

export default function WorkbenchPage() {
    const { t } = useTranslation();
    const router = useRouter();
    const [activeTab, setActiveTab] = useState('0');
    const swiperRef = useRef<any>(null);

    // 使用虚拟数据
    const allBots = mockWorkbenchData.data.items;

    // 根据当前 tab 过滤数据
    const botList = useMemo(() => {
        let filtered = allBots;

        // 按类型过滤
        const botType = Number(activeTab);
        if (botType !== 0) {
            filtered = filtered.filter(bot => bot.bot_type === botType);
        }

        return filtered;
    }, [activeTab, allBots]);

    const tabItems = [
        { key: '0', title: '全部' },
        { key: '1', title: 'Pilot' },
        { key: '2', title: 'LobeChat' },
        { key: '3', title: 'Chatflow' },
    ];

    // bot_type 映射
    const botTypeMap: { [key: number]: string } = {
        1: 'Pilot',
        2: 'LobeChat',
        3: 'Chatflow',
    };

    const handleTabChange = (key: string) => {
        setActiveTab(key);
    };

    // 当 activeTab 改变时，同步 Swiper
    useEffect(() => {
        const index = tabItems.findIndex((item) => item.key === activeTab);
        if (index !== -1 && swiperRef.current) {
            swiperRef.current.swipeTo(index);
        }
    }, [activeTab]);

    // 渲染列表项
    const renderListItem = (item: any) => (
        <div
            key={item.id}
            className="bg-[var(--color-bg)] mx-3 mt-3 rounded-lg shadow-sm border border-[var(--color-border)] p-4 active:bg-[var(--color-bg-hover)] cursor-pointer"
            onClick={() => {
                // 将应用信息存储到 sessionStorage，供详情页使用
                sessionStorage.setItem('currentBot', JSON.stringify(item));
                router.push(`/workbench/detail?id=${item.id}`);
            }}
        >
            <div className="flex items-start space-x-3">
                {/* 缩略图 */}
                <div className="flex-shrink-0 relative">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full overflow-hidden">
                        <Image
                            src="/avatars/04.svg"
                            alt={item.name}
                            width={64}
                            height={64}
                            className="w-full h-full object-cover"
                        />
                    </div>
                </div>

                {/* 内容区域 */}
                <div className="flex-1 min-w-0">
                    {/* 名称和状态 */}
                    <div className="flex items-center justify-between mb-1.5">
                        <h3 className="text-base font-medium text-[var(--color-text-1)]">
                            {item.name}
                        </h3>
                        <div className="flex items-center space-x-1.5">
                            <div
                                className={`w-2 h-2 rounded-full ${item.online ? 'bg-blue-500' : 'bg-gray-400'
                                    }`}
                            ></div>
                            <span
                                className={`text-xs ${item.online ? 'text-blue-500' : 'text-gray-400'
                                    }`}
                            >
                                {item.online ? '在线' : '下线'}
                            </span>
                        </div>
                    </div>

                    {/* 描述文本 */}
                    <p className="text-xs text-[var(--color-text-2)] mb-3 leading-relaxed overflow-hidden"
                        style={{
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis'
                        }}>
                        {item.introduction || '暂无简介'}
                    </p>

                    {/* 标签按钮 */}
                    {item.bot_type && (
                        <span
                            className=" float-right px-3 py-1 text-xs font-medium text-gray-800 bg-gray-200 rounded"
                        >
                            {botTypeMap[item.bot_type] || '未知类型'}
                        </span>
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

    return (
        <div className="flex flex-col h-screen bg-[var(--color-background-body)]">
            {/* 标签栏和搜索图标 */}
            <div className="bg-[var(--color-bg)] flex items-center">
                <div className="flex-1">
                    <style dangerouslySetInnerHTML={{
                        __html: `
                            .adm-tabs-header {
                                color: var(--color-text-1) !important;
                                border-bottom: none !important;
                            }
                        `
                    }} />
                    <Tabs
                        activeKey={activeTab}
                        onChange={handleTabChange}
                        style={{
                            '--title-font-size': '15px',
                            '--content-padding': '0',
                        }}
                    >
                        {tabItems.map((item) => (
                            <Tabs.Tab title={item.title} key={item.key} />
                        ))}
                    </Tabs>
                </div>
                <div className="px-4 py-3">
                    <SearchOutline
                        fontSize={22}
                        className="text-[var(--color-text-2)]"
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
                                {botList.map((item) => renderListItem(item))}
                                {botList.length === 0 && renderEmptyState()}
                            </div>
                        </Swiper.Item>
                    );
                })}
            </Swiper>
            <BottomTabBar />
        </div>
    );
}
