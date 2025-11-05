'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Switch, List, ImageViewer } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';
import Image from 'next/image';
import { mockChatData } from '@/constants/mockData';

export default function AppDetailPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const id = searchParams.get('id') || '';

    // 从 sessionStorage 获取真实的 bot 数据
    const [botData, setBotData] = useState<any>(null);
    const [receiveNotification, setReceiveNotification] = useState(true);
    const [avatarVisible, setAvatarVisible] = useState(false);

    useEffect(() => {
        const foundBot = mockChatData.find((bot) => bot.id === id);
        if (foundBot) {
            setBotData(foundBot);
        } else {
            const storedBotString = sessionStorage.getItem('currentBot');
            if (storedBotString) {
                try {
                    const bot = JSON.parse(storedBotString);
                    setBotData(bot);
                } catch (error) {
                    console.error('解析 bot 数据失败:', error);
                }
            }
        }
    }, [id]);

    if (!botData) {
        return (
            <div className="flex flex-col items-center justify-center h-screen bg-gray-50">
                <div className="text-gray-400 text-lg">应用不存在</div>
                <button
                    onClick={() => router.back()}
                    className="mt-4 px-6 py-2 bg-blue-500 text-white rounded-lg"
                >
                    返回
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
                    <h1 className="text-lg font-medium text-[var(--color-text-1)]">{botData.lastMessage ? '对话设置' : '应用简介'}</h1>
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
                                src={botData.avatar || '/avatars/04.svg'}
                                alt={botData.name}
                                width={96}
                                height={96}
                                className="w-full h-full object-cover"
                            />
                        </div>

                        {/* 头像查看器 */}
                        <ImageViewer
                            image={botData.avatar || '/avatars/04.svg'}
                            visible={avatarVisible}
                            onClose={() => setAvatarVisible(false)}
                        />

                        {/* 应用名称 */}
                        <h2 className="text-xl font-semibold text-[var(--color-text-1)] mb-2">
                            {botData.name}
                        </h2>

                        {/* 在线状态 */}
                        <div className="flex items-center space-x-1.5 mb-3">
                            <div
                                className={`w-2 h-2 rounded-full ${botData.online ? 'bg-blue-500' : 'bg-gray-400'}`}
                            ></div>
                            <span className={`text-sm ${botData.online ? 'text-blue-500' : 'text-gray-400'}`}>
                                {botData.online ? '在线' : '下线'}
                            </span>
                        </div>

                        <p className="text-sm text-[var(--color-text-2)] text-center">
                            {botData.introduction || '暂无简介'}
                        </p>

                    </div>
                </div>

                {/* 设置选项 */}
                <div className="mt-2">
                    {botData.lastMessage && (
                        <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-3xl shadow-sm overflow-hidden">
                            <List>
                                <List.Item prefix={<span className="iconfont icon-duihualishi text-2xl"></span>}
                                    onClick={() => {
                                        router.push(`/search?type=ChatHistory&id=${botData.id}`);
                                    }}>
                                    查找聊天记录
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
                                接收通知
                            </List.Item>
                        </List>
                    </div>

                    <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-3xl shadow-sm overflow-hidden">
                        <List>
                            <List.Item prefix={<span className="iconfont icon-liaotianduihua-xianxing text-2xl"></span>}
                                onClick={() => {
                                    router.push(`/conversation?id=${botData.id}`);
                                }}>
                                {botData.lastMessage ? '继续对话' : '快速发起对话'}
                            </List.Item>
                        </List>
                    </div>
                </div>
            </div>
        </div>
    );
}