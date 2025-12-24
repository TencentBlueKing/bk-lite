'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Switch, List, ImageViewer, SpinLoading } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';
import Image from 'next/image';
import { useTranslation } from '@/utils/i18n';
import { getApplication } from '@/api/bot';
import { getAvatar } from '@/utils/avatar';

export default function AppDetailPage() {
    const { t } = useTranslation();
    const router = useRouter();
    const searchParams = useSearchParams();
    const botId = searchParams?.get('bot_id') || '';

    const [botData, setBotData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [receiveNotification, setReceiveNotification] = useState(true);
    const [avatarVisible, setAvatarVisible] = useState(false);

    useEffect(() => {
        if (!botId) {
            setLoading(false);
            return;
        }

        const fetchDetail = async () => {
            try {
                const response = await getApplication({ bot: Number(botId) });
                if (response?.result && response?.data) {
                    setBotData(response.data[0]);
                }
            } catch (error) {
                console.error('获取应用详情失败:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchDetail();
    }, [botId]);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-[var(--color-background-body)]">
                <SpinLoading color="primary" />
            </div>
        );
    }

    if (!botData) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-[var(--color-background-body)]">
                <div className="text-[var(--color-text-3)] text-lg">{t('workbench.appNotExist')}</div>
                <button
                    onClick={() => router.back()}
                    className="mt-4 px-6 py-2 bg-blue-500 text-white rounded-lg"
                >
                    {t('common.back')}
                </button>
            </div>
        );
    }

    const handleNotificationChange = (checked: boolean) => {
        setReceiveNotification(checked);
    };

    return (
        <div className="flex flex-col h-screen bg-[var(--color-background-body)]">
            {/* 顶部导航栏 */}
            <div className="bg-[var(--color-bg)]">
                <div className="flex items-center justify-center relative px-4 py-3">
                    <button onClick={() => router.back()} className="absolute left-4">
                        <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" />
                    </button>
                    <h1 className="text-lg font-medium text-[var(--color-text-1)]">{t('workbench.appIntroduction')}</h1>
                </div>
            </div>

            {/* 内容区域 */}
            <div className="flex-1 overflow-auto">
                {/* 应用头部信息 */}
                <div className="px-4 py-6">
                    <div className="flex flex-col items-center">
                        {/* 应用图标 */}
                        <div
                            className="w-24 h-24 mb-4 cursor-pointer"
                            onClick={() => setAvatarVisible(true)}
                        >
                            <Image
                                src={getAvatar(botData.id)}
                                alt={botData.app_name}
                                width={96}
                                height={96}
                                className="w-full h-full object-cover"
                            />
                        </div>

                        {/* 头像查看器 */}
                        <ImageViewer
                            image={getAvatar(botData.id)}
                            visible={avatarVisible}
                            onClose={() => setAvatarVisible(false)}
                        />

                        {/* 应用名称 */}
                        <h2 className="text-xl font-semibold text-[var(--color-text-1)] mb-2">
                            {botData.app_name}
                        </h2>

                        {/* 在线状态 - 默认在线 */}
                        <div className="flex items-center space-x-1.5 mb-3">
                            <div className="w-2 h-2 rounded-full bg-green-500"></div>
                            <span className="text-sm text-green-500">
                                {t('common.online')}
                            </span>
                        </div>

                        <p className="text-sm text-[var(--color-text-4)] text-center">
                            {botData.app_description || t('workbench.noIntroduction')}
                        </p>

                    </div>
                </div>

                {/* 设置选项 */}
                <div className="mt-2">
                    {/* 查找历史记录 */}
                    {botData.lastMessage && (
                        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-3xl shadow-sm overflow-hidden">
                            <List>
                                <List.Item prefix={<span className="iconfont icon-duihualishi text-2xl"></span>}
                                    onClick={() => {
                                        router.push(`/search?type=ChatHistory&id=${botData.id}`);
                                    }}>
                                    {t('workbench.searchChatHistory')}
                                </List.Item>
                            </List>
                        </div>
                    )}

                    {/* 接收通知 */}
                    <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-3xl shadow-sm overflow-hidden">
                        <List>
                            <List.Item prefix={<span className="iconfont icon-tongzhi text-2xl"></span>}
                                extra={<Switch checked={receiveNotification}
                                    onChange={handleNotificationChange}
                                    style={{
                                        '--checked-color': '#1677ff',
                                    }} />}>
                                {t('workbench.receiveNotification')}
                            </List.Item>
                        </List>
                    </div>

                    <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-3xl shadow-sm overflow-hidden">
                        <List>
                            <List.Item prefix={<span className="iconfont icon-liaotianduihua-xianxing text-2xl"></span>}
                                onClick={() => {
                                    router.push(`/conversation?bot_id=${botData.bot}`);
                                }}>
                                {botData.lastMessage ? t('workbench.continueConversation') : t('workbench.startConversation')}
                            </List.Item>
                        </List>
                    </div>
                </div>
            </div>
        </div>
    );
}