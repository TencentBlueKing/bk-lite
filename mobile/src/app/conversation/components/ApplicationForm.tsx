import React, { useState, useRef, memo, useEffect } from 'react';
import { Button, Input, Toast, DatePicker } from 'antd-mobile';

interface FormField {
    label: string;
    type: 'text' | 'datetime' | 'file';
    name: string;
    value?: any;
    required: boolean;
    editable: boolean;
}

interface ApplicationFormProps {
    field: FormField[];
    state: 'noSubmitted' | 'submitted';
    onSubmit?: (formData: Record<string, any>) => void;
}

const ApplicationFormComponent: React.FC<ApplicationFormProps> = ({
    field,
    state: initialState,
    onSubmit
}) => {
    const [formState, setFormState] = useState<'noSubmitted' | 'submitted'>(initialState);
    const [formData, setFormData] = useState<Record<string, any>>(() => {
        // 使用惰性初始化，只在组件挂载时执行一次
        const initialData: Record<string, any> = {};
        field.forEach(f => {
            if (f.value !== undefined && f.value !== null && f.value !== '') {
                initialData[f.name] = f.value;
            }
        });
        return initialData;
    });
    const [datePickerVisible, setDatePickerVisible] = useState<string | null>(null);
    const [hasScroll, setHasScroll] = useState(false);
    const formFieldsRef = useRef<HTMLDivElement>(null);

    // 使用 ResizeObserver 监听容器大小变化，检测滚动条
    useEffect(() => {
        const element = formFieldsRef.current;
        if (!element) return;

        const checkScroll = () => {
            const scrollable = element.scrollHeight > element.clientHeight;
            setHasScroll(scrollable);
        };

        // 初始检测
        checkScroll();

        // 使用 ResizeObserver 监听内容变化
        const resizeObserver = new ResizeObserver(() => {
            checkScroll();
        });

        resizeObserver.observe(element);

        return () => {
            resizeObserver.disconnect();
        };
    }, []); // 空依赖数组，只在挂载时设置

    const handleFieldChange = (name: string, value: any) => {
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
    };

    const handleSubmit = () => {
        // 验证必填字段
        const missingFields = field
            .filter(f => f.required && !formData[f.name])
            .map(f => f.label);

        if (missingFields.length > 0) {
            Toast.show({
                icon: 'fail',
                content: `请填写必填字段: ${missingFields.join(', ')}`,
            });
            return;
        }

        // 提交表单
        setFormState('submitted');
        onSubmit?.(formData);
        Toast.show({
            icon: 'success',
            content: '申请表已提交，等待审核',
        });
    };

    const renderField = (fieldInfo: FormField) => {
        const { label, type, name, required, editable, value: initialValue } = fieldInfo;
        const value = formData[name] ?? initialValue ?? '';

        // 格式化显示值
        const displayValue = Array.isArray(value) ? value.join(', ') : value;
        const dateValue = type === 'datetime' && value ? new Date(value) : undefined;

        return (
            <div key={name} className="mb-3 flex items-center gap-3">
                <div className="flex items-center min-w-[70px]">
                    <span className="text-sm text-[var(--color-text-1)]">
                        {label}
                    </span>
                    {required && (
                        <span className="text-red-500 ml-1 text-xs">*</span>
                    )}
                </div>

                <div className="flex-1">
                    {type === 'text' && (
                        <Input
                            value={displayValue}
                            onChange={(val) => handleFieldChange(name, val)}
                            placeholder={`请输入${label}`}
                            disabled={!editable || formState === 'submitted'}
                            className="border border-[var(--color-border)] rounded-lg"
                            style={{ '--font-size': '13px' } as any}
                        />
                    )}

                    {type === 'datetime' && (
                        <>
                            <div
                                onClick={() => {
                                    if (editable && formState !== 'submitted') {
                                        setDatePickerVisible(name);
                                    }
                                }}
                                className={`border border-[var(--color-border)] rounded-lg px-2 py-1.5 text-xs ${!editable || formState === 'submitted'
                                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                    : 'bg-white text-[var(--color-text-1)] cursor-pointer'
                                    }`}
                            >
                                {dateValue ? dateValue.toLocaleString('zh-CN', {
                                    year: 'numeric',
                                    month: '2-digit',
                                    day: '2-digit',
                                    hour: '2-digit',
                                    minute: '2-digit'
                                }) : `请选择${label}`}
                            </div>
                            <DatePicker
                                visible={datePickerVisible === name}
                                onClose={() => setDatePickerVisible(null)}
                                precision="minute"
                                onConfirm={(val) => {
                                    handleFieldChange(name, val);
                                    setDatePickerVisible(null);
                                }}
                                value={dateValue}
                            />
                        </>
                    )}

                    {type === 'file' && (
                        <div className="border border-[var(--color-border)] rounded-lg p-1.5">
                            <input
                                type="file"
                                onChange={(e) => handleFieldChange(name, e.target.files?.[0])}
                                disabled={!editable || formState === 'submitted'}
                                className="w-full text-xs text-[var(--color-text-2)]"
                            />
                        </div>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="w-full">
            <div className="bg-[var(--color-fill-2)] rounded-2xl p-4">

                {/* 表单字段区域 - 最大高度300px，超出滚动 */}
                <div
                    ref={formFieldsRef}
                    className="max-h-[300px] overflow-y-auto"
                    style={{ scrollbarWidth: 'thin' }}
                >
                    {field.map(renderField)}
                </div>

                {/* 滚动提示 - 仅当内容真正超出时显示 */}
                {hasScroll && (
                    <div className="text-xs text-[var(--color-text-3)] text-center mt-2 mb-2">
                        ↕ 滑动查看更多
                    </div>
                )}

                <div className="mt-4">
                    {formState === 'noSubmitted' ? (
                        <Button
                            color="primary"
                            block
                            onClick={handleSubmit}
                            className="rounded-lg"
                        >
                            提交申请
                        </Button>
                    ) : (
                        <Button
                            color="default"
                            block
                            disabled
                            className="rounded-lg"
                        >
                            <span>已提交</span>
                        </Button>
                    )}
                </div>
            </div>
        </div>
    );
};

// 使用 memo 包装组件，深度比较 props，避免不必要的重渲染
export const ApplicationForm = memo(ApplicationFormComponent, (prevProps, nextProps) => {
    // 只有当 state 改变时才重新渲染，忽略 field 的引用变化
    return prevProps.state === nextProps.state && prevProps.field.length === nextProps.field.length;
});
