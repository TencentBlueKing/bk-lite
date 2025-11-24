'use client';
import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { List, Input, Button, Toast, Picker } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';
import { mockAccountInfo } from '@/constants/mockData';

// 时区选项
const timezoneOptions = [
    [
        { label: '亚洲/上海 (UTC+08:00)', value: 'Asia/Shanghai' },
        { label: '亚洲/东京 (UTC+09:00)', value: 'Asia/Tokyo' },
        { label: '美国/纽约 (UTC-05:00)', value: 'America/New_York' },
        { label: '美国/洛杉矶 (UTC-08:00)', value: 'America/Los_Angeles' },
        { label: '欧洲/伦敦 (UTC+00:00)', value: 'Europe/London' },
        { label: '欧洲/巴黎 (UTC+01:00)', value: 'Europe/Paris' },
    ],
];

// 语言选项
const languageOptions = [
    [
        { label: '中文(简体)', value: 'zh' },
        { label: 'English', value: 'en' },
    ],
];

export default function AccountDetailsPage() {
    const router = useRouter();

    // 可编辑字段
    const [displayName, setDisplayName] = useState('');
    const [email, setEmail] = useState('');
    const [timezone, setTimezone] = useState('Asia/Shanghai');
    const [language, setLanguage] = useState('zh');

    // 原始值用于比较
    const [originalData, setOriginalData] = useState({
        displayName: '',
        email: '',
        timezone: 'Asia/Shanghai',
        language: 'zh',
    });

    const [timezonePickerVisible, setTimezonePickerVisible] = useState(false);
    const [languagePickerVisible, setLanguagePickerVisible] = useState(false);
    const [isModified, setIsModified] = useState(false);
    const [isSaving, setIsSaving] = useState(false);

    // 初始化数据
    useEffect(() => {
        // 使用 mock 数据初始化
        const initialData = {
            displayName: mockAccountInfo.displayName,
            email: mockAccountInfo.email,
            timezone: mockAccountInfo.timezone,
            language: mockAccountInfo.language,
        };
        setDisplayName(initialData.displayName);
        setEmail(initialData.email);
        setTimezone(initialData.timezone);
        setLanguage(initialData.language);
        setOriginalData(initialData);
    }, []);

    // 检查是否有修改
    useEffect(() => {
        const hasChanges =
            displayName !== originalData.displayName ||
            email !== originalData.email ||
            timezone !== originalData.timezone ||
            language !== originalData.language;
        setIsModified(hasChanges);
    }, [displayName, email, timezone, language, originalData]);

    // 获取时区显示文本
    const getTimezoneLabel = (value: string) => {
        const option = timezoneOptions[0].find((opt) => opt.value === value);
        return option ? option.label : value;
    };

    // 获取语言显示文本
    const getLanguageLabel = (value: string) => {
        const option = languageOptions[0].find((opt) => opt.value === value);
        return option ? option.label : value;
    };

    // 保存修改
    const handleSave = async () => {
        setIsSaving(true);
        try {
            // TODO: 调用 API 保存修改
            console.log('保存账户信息数据:', {
                displayName,
                email,
                timezone,
                language,
            });
            // 更新原始数据
            setOriginalData({
                displayName,
                email,
                timezone,
                language,
            });

            Toast.show({
                content: '保存成功',
                icon: 'success',
            });

            setIsModified(false);
        } catch (error) {
            console.error('保存失败:', error);
            Toast.show({
                content: '保存失败',
                icon: 'fail',
            });
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-[var(--color-background-body)]">
            {/* 顶部导航栏 */}
            <div className="flex items-center justify-center px-4 py-3 bg-[var(--color-bg)]">
                <button onClick={() => router.back()} className="absolute left-4">
                    <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" />
                </button>
                <h1 className="text-lg font-medium text-[var(--color-text-1)]">
                    账号与安全
                </h1>
                <span className='absolute right-4'>
                    <Button
                        color="primary"
                        loading={isSaving}
                        onClick={handleSave}
                        disabled={!isModified}
                        size="mini"
                        className='rounded-lg'
                    >
                        保存
                    </Button>
                </span>
            </div>

            {/* 内容区域 */}
            <div className="flex-1 overflow-y-auto">
                {/* 基本信息卡片 */}
                <div className="mx-4 mt-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
                    <List>
                        {/* 用户名 - 不可编辑 */}
                        <List.Item
                            prefix={
                                <div className="flex items-center justify-center w-6 h-6">
                                    <span className="iconfont icon-yonghuming text-[var(--color-text-1)] text-2xl"></span>
                                </div>
                            }
                            extra={
                                <span className="text-[var(--color-text-3)] text-sm">
                                    {mockAccountInfo.username}
                                </span>
                            }
                        >
                            <span className="text-[var(--color-text-1)] text-base">用户名</span>
                        </List.Item>

                        {/* 姓名 - 可编辑 */}
                        <List.Item
                            prefix={
                                <div className="flex items-center justify-center w-6 h-6">
                                    <span className="iconfont icon-xingming text-[var(--color-text-1)] text-xl"></span>
                                </div>
                            }
                        >
                            <div className="flex items-center justify-between w-full">
                                <span className="text-[var(--color-text-1)] text-base mr-4">姓名</span>
                                <Input
                                    value={displayName}
                                    onChange={setDisplayName}
                                    placeholder="请输入姓名"
                                    className="flex-1 text-right"
                                    style={{
                                        '--font-size': '14px',
                                        '--text-align': 'right',
                                    }}
                                />
                            </div>
                        </List.Item>

                        {/* 邮箱 - 可编辑 */}
                        <List.Item
                            prefix={
                                <div className="flex items-center justify-center w-6 h-6">
                                    <span className="iconfont icon-youxiang text-[var(--color-text-1)] text-xl"></span>
                                </div>
                            }
                        >
                            <div className="flex items-center justify-between w-full">
                                <span className="text-[var(--color-text-1)] text-base mr-4">邮箱</span>
                                <Input
                                    value={email}
                                    onChange={setEmail}
                                    placeholder="请输入邮箱"
                                    type="email"
                                    className="flex-1 text-right"
                                    style={{
                                        '--font-size': '14px',
                                        '--text-align': 'right',
                                    }}
                                />
                            </div>
                        </List.Item>

                        {/* 时区 - 下拉选择 */}
                        <List.Item
                            prefix={
                                <div className="flex items-center justify-center w-6 h-6">
                                    <span className="iconfont icon-shiqu text-[var(--color-text-1)] text-xl"></span>
                                </div>
                            }
                            onClick={() => setTimezonePickerVisible(true)}
                            clickable
                        >
                            <div className="flex items-center justify-between w-full">
                                <span className="text-[var(--color-text-1)] text-base">时区</span>
                                <span className="text-[var(--color-text-1)] text-sm">
                                    {getTimezoneLabel(timezone)}
                                </span>
                            </div>
                        </List.Item>

                        {/* 语言 - 下拉选择 */}
                        <List.Item
                            prefix={
                                <div className="flex items-center justify-center w-6 h-6">
                                    <span className="iconfont icon-yuyan text-[var(--color-text-1)] text-2xl"></span>
                                </div>
                            }
                            onClick={() => setLanguagePickerVisible(true)}
                            clickable
                        >
                            <div className="flex items-center justify-between w-full">
                                <span className="text-[var(--color-text-1)] text-base">语言</span>
                                <span className="text-[var(--color-text-1)] text-sm">
                                    {getLanguageLabel(language)}
                                </span>
                            </div>
                        </List.Item>
                    </List>
                </div>

                {/* 组织信息卡片 */}
                <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
                    <List header={<span className='text-[var(--color-text-1)]'><span className='iconfont icon-zuzhijigou text-xl'></span><span className="text-base px-4">组织</span></span>}>
                        <List.Item>
                            <div className="flex flex-wrap gap-2">
                                {mockAccountInfo.organizations.map((org, index) => (
                                    <div
                                        key={index}
                                        className="px-3 py-1 bg-[var(--color-fill-2)] rounded text-[var(--color-text-3)] text-sm"
                                    >
                                        {org}
                                    </div>
                                ))}
                            </div>
                        </List.Item>
                    </List>
                </div>

                {/* 角色信息卡片 */}
                <div className="mx-4 mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden">
                    <List header={
                        <div className="flex items-center justify-between">
                            <span className='text-[var(--color-text-1)]'>
                                <span className="iconfont icon-jiaoseguanli text-3xl"></span>
                                <span className="text-base px-3">角色</span>
                            </span>
                            <span className="text-[var(--color-text-3)] text-sm">{mockAccountInfo.userType}</span>
                        </div>
                    }>
                        <List.Item>
                            <div className="flex flex-wrap gap-2">
                                {mockAccountInfo.roles.map((role, index) => (
                                    <div
                                        key={index}
                                        className="px-3 py-1 bg-[var(--color-fill-2)] rounded text-[var(--color-text-3)] text-sm"
                                    >
                                        {role}
                                    </div>
                                ))}
                            </div>
                        </List.Item>
                    </List>
                </div>
            </div>

            {/* 时区选择器 */}
            <Picker
                columns={timezoneOptions}
                visible={timezonePickerVisible}
                onClose={() => setTimezonePickerVisible(false)}
                value={[timezone]}
                onConfirm={(value) => {
                    setTimezone(value[0] as string);
                }}
            />

            {/* 语言选择器 */}
            <Picker
                className='bg-[var(--color-bg)]'
                columns={languageOptions}
                visible={languagePickerVisible}
                onClose={() => setLanguagePickerVisible(false)}
                value={[language]}
                onConfirm={(value) => {
                    setLanguage(value[0] as string);
                }}
            />
        </div>
    );
}
