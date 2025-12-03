'use client';
import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Form, Input, Button, Toast, Picker, SpinLoading } from 'antd-mobile';
import { LeftOutline } from 'antd-mobile-icons';
import { useTranslation } from '@/utils/i18n';
import { useAuth } from '@/context/auth';
import { timezoneOptions, languageOptions } from '@/constants/userPicker';
import { getUserInfo, updateUserInfo } from '@/api/user';



export default function AccountDetailsPage() {
    const { t } = useTranslation();
    const { updateUserInfo: updateStoredUserInfo } = useAuth();
    const router = useRouter();
    const [form] = Form.useForm();
    const [loading, setLoading] = useState(false);
    const [originalData, setOriginalData] = useState<Record<string, any>>({});
    const [currentTimezone, setCurrentTimezone] = useState('Asia/Shanghai');
    const [currentLocale, setCurrentLocale] = useState('zh-Hans');
    const [isModified, setIsModified] = useState(false);
    const [isSaving, setIsSaving] = useState(false);

    useEffect(() => {
        fetchUserInfo();
    }, []);

    const fetchUserInfo = async () => {
        setLoading(true);
        try {
            const response = await getUserInfo();
            if (!response.result) {
                const errorMessage = response.message || t('login.systemError');
                Toast.show({ content: errorMessage, icon: 'fail' });
                return;
            }
            const data = response.data;
            setOriginalData(data);
            form.setFieldsValue({
                display_name: data.display_name,
                email: data.email,
            });
            setCurrentTimezone(data.timezone);
            setCurrentLocale(data.locale);
        } catch (error) {
            console.error('Failed to fetch user info:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleValuesChange = (newTimezone?: string, newLocale?: string) => {
        const currentValues = form.getFieldsValue();
        const tz = newTimezone ?? currentTimezone;
        const locale = newLocale ?? currentLocale;
        const hasChanges =
            currentValues.display_name !== originalData.display_name ||
            currentValues.email !== originalData.email ||
            tz !== originalData.timezone ||
            locale !== originalData.locale;
        setIsModified(hasChanges);
    };

    const handleSave = async () => {
        try {
            await form.validateFields();
            setIsSaving(true);
            const formValues = form.getFieldsValue();
            const saveData = {
                display_name: formValues.display_name,
                email: formValues.email,
                timezone: currentTimezone,
                locale: currentLocale,
            };
            const response = await updateUserInfo(saveData);
            if (!response.result) {
                const errorMessage = response.message || t('account.saveFailed');
                Toast.show({ content: errorMessage, icon: 'fail' });
                return;
            }
            setOriginalData(prev => ({
                ...prev,
                ...saveData,
            }));

            await updateStoredUserInfo({
                display_name: saveData.display_name,
                locale: saveData.locale,
            });

            Toast.show({
                content: t('account.saveSuccess'),
                icon: 'success',
            });
            setIsModified(false);
        } catch (error) {
            console.error('保存失败:', error);
            Toast.show({
                content: t('account.saveFailed'),
                icon: 'fail',
            });
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="flex flex-col h-full bg-[var(--color-background-body)]">
            <div className="flex items-center justify-center px-4 py-3 bg-[var(--color-bg)]">
                <button onClick={() => router.back()} className="absolute left-4">
                    <LeftOutline fontSize={24} className="text-[var(--color-text-1)]" />
                </button>
                <h1 className="text-lg font-medium text-[var(--color-text-1)]">
                    {t('account.title')}
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
                        {t('common.save')}
                    </Button>
                </span>
            </div>
            {loading ? (
                <div className="flex-1 flex items-center justify-center">
                    <SpinLoading color="primary" style={{ '--size': '32px' }} />
                </div>
            ) : <div className="flex-1 overflow-y-auto px-4 pt-4">
                {/* 基本信息卡片 */}
                <div className="mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm">
                    <Form
                        form={form}
                        onValuesChange={handleValuesChange}
                        mode='card'
                        layout='horizontal'
                        style={{
                            '--adm-form-item-feedback-font-size': '12px',
                        } as React.CSSProperties}
                        className="[&_.adm-form-item-feedback-error]:text-right"
                    >
                        {/* 用户名 - 不可编辑 */}
                        <Form.Item
                            label={
                                <div className="flex items-center">
                                    <span className="iconfont icon-yonghuming text-[var(--color-text-1)] text-xl mr-2"></span>
                                    <span className="text-[var(--color-text-1)] text-base">{t('account.username')}</span>
                                </div>
                            }
                        >
                            <div className="text-[var(--color-text-3)] text-sm text-right">{originalData.username as string}</div>
                        </Form.Item>

                        {/* 姓名 - 可编辑必填 */}
                        <Form.Item
                            name="display_name"
                            label={
                                <div className="flex items-center whitespace-nowrap">
                                    <span className="iconfont icon-xingming text-[var(--color-text-1)] text-lg mr-2"></span>
                                    <span className="text-[var(--color-text-1)] text-base">{t('account.displayName')}</span>
                                </div>
                            }
                            rules={[{ required: true, message: t('account.enterName') }]}
                            style={{ '--prefix-width': '9em' } as React.CSSProperties}
                        >
                            <Input
                                placeholder={t('account.enterName')}
                                style={{
                                    '--font-size': '14px',
                                    '--text-align': 'right',
                                }}
                            />
                        </Form.Item>

                        {/* 邮箱 - 可编辑必填 */}
                        <Form.Item
                            name="email"
                            label={
                                <div className="flex items-center">
                                    <span className="iconfont icon-youxiang text-[var(--color-text-1)] text-lg mr-2"></span>
                                    <span className="text-[var(--color-text-1)] text-base">{t('account.email')}</span>
                                </div>
                            }
                            rules={[
                                { required: true, message: t('account.enterEmail') },
                                { type: 'email', message: t('account.enterValidEmail') },
                            ]}
                        >
                            <Input
                                placeholder={t('account.enterEmail')}
                                type="email"
                                style={{
                                    '--font-size': '14px',
                                    '--text-align': 'right',
                                }}
                            />
                        </Form.Item>

                        {/* 时区 - 下拉选择 */}
                        <Form.Item
                            label={
                                <div className="flex items-center">
                                    <span className="iconfont icon-shiqu text-[var(--color-text-1)] text-lg mr-2"></span>
                                    <span className="text-[var(--color-text-1)] text-base">{t('account.timezone')}</span>
                                </div>
                            }
                        >
                            <Picker
                                columns={[timezoneOptions.map(opt => ({ label: t(opt.label), value: opt.value }))]}
                                value={[currentTimezone]}
                                onConfirm={(value) => {
                                    const newValue = value[0] as string;
                                    setCurrentTimezone(newValue);
                                    handleValuesChange(newValue, undefined);
                                }}
                            >
                                {(items, actions) => (
                                    <div onClick={() => actions.open()} className="text-[var(--color-text-1)] text-sm cursor-pointer text-right">
                                        {timezoneOptions.find(o => o.value === currentTimezone)
                                            ? t(timezoneOptions.find(o => o.value === currentTimezone)!.label)
                                            : ''}
                                    </div>
                                )}
                            </Picker>
                        </Form.Item>

                        {/* 语言 - 下拉选择 */}
                        <Form.Item
                            label={
                                <div className="flex items-center">
                                    <span className="iconfont icon-yuyan text-[var(--color-text-1)] text-xl mr-2"></span>
                                    <span className="text-[var(--color-text-1)] text-base">{t('account.language')}</span>
                                </div>
                            }
                        >
                            <Picker
                                columns={[languageOptions.map(opt => ({ label: t(opt.label), value: opt.value }))]}
                                value={[currentLocale]}
                                onConfirm={(value) => {
                                    const newValue = value[0] as string;
                                    setCurrentLocale(newValue);
                                    handleValuesChange(undefined, newValue);
                                }}
                            >
                                {(items, actions) => (
                                    <div onClick={() => actions.open()} className="text-[var(--color-text-1)] text-sm cursor-pointer text-right">
                                        {languageOptions.find(o => o.value === currentLocale)
                                            ? t(languageOptions.find(o => o.value === currentLocale)!.label)
                                            : ''}
                                    </div>
                                )}
                            </Picker>
                        </Form.Item>
                    </Form>
                </div>

                {/* 组织信息卡片 */}
                <div className="mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden p-4">
                    <div className="flex items-center mb-3">
                        <span className="iconfont icon-zuzhijigou text-[var(--color-text-1)] text-xl mr-2"></span>
                        <span className="text-[var(--color-text-1)] text-base">{t('account.organization')}</span>
                    </div>
                    <div className="flex flex-wrap gap-2">

                        {originalData.group_list && originalData.group_list.length > 0 ? (
                            originalData.group_list.map((group: string, index: number) => (
                                <div
                                    key={index}
                                    className="px-3 py-1 bg-[var(--color-fill-2)] rounded text-[var(--color-text-3)] text-sm"
                                >
                                    {group}
                                </div>
                            ))
                        ) : (
                            <span className="text-gray-400">{t('common.noData')}</span>
                        )}
                    </div>
                </div>

                {/* 角色信息卡片 */}
                <div className="mb-4 bg-[var(--color-bg)] rounded-2xl shadow-sm overflow-hidden p-4">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center">
                            <span className="iconfont icon-jiaoseguanli text-[var(--color-text-1)] text-3xl mr-2"></span>
                            <span className="text-[var(--color-text-1)] text-base">{t('account.role')}</span>
                        </div>
                        <span className="text-[var(--color-text-3)] text-sm">
                            {originalData.role_list?.some((role: any) => !role.app && role.name === 'admin')
                                ? t('account.superAdmin')
                                : t('account.normalUser')}
                        </span>
                    </div>
                    <hr className="border-[var(--color-border)] mb-3" />
                    <div className="flex flex-wrap gap-3">
                        {originalData.role_list && originalData.role_list.length > 0 ? (
                            (() => {
                                const superAdmin = originalData.role_list.find((role: any) => !role.app && role.name === 'admin');
                                const normalRoles = originalData.role_list.filter((role: any) => !((!role.app) && role.name === 'admin'));
                                const groupedRoles = normalRoles.reduce((acc: any, role: any) => {
                                    const appName = role.app_display_name || t('account.otherApp');
                                    if (!acc[appName]) {
                                        acc[appName] = [];
                                    }
                                    acc[appName].push(role);
                                    return acc;
                                }, {});

                                return (
                                    <>
                                        {/* 超级管理员 */}
                                        {superAdmin && (
                                            <div className="flex flex-wrap gap-2">
                                                <div className="px-3 py-1 bg-[var(--color-fill-2)] rounded text-[var(--color-text-3)] text-sm">
                                                    {t('account.superAdmin')}
                                                </div>
                                            </div>
                                        )}
                                        {/* 按应用分组的角色 */}
                                        {Object.entries(groupedRoles).map(([app, roles]: [string, any]) => (
                                            <div key={app}>
                                                <div className="text-[var(--color-text-3)] text-xs mb-2 relative pl-2 before:content-[''] before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-1 before:h-full before:bg-blue-500 before:rounded-full">
                                                    {app}
                                                </div>
                                                <div className="flex flex-wrap gap-2">
                                                    {roles.map((role: any, idx: number) => (
                                                        <div
                                                            key={idx}
                                                            className="px-3 py-1 bg-[var(--color-fill-2)] rounded text-[var(--color-text-3)] text-sm"
                                                        >
                                                            {role.name}
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </>
                                );
                            })()
                        ) : (
                            <span className="text-gray-400">{t('common.noData')}</span>
                        )}
                    </div>
                </div>
            </div>}
        </div >
    );
}
