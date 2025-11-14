import React, { useState, useRef, memo, useEffect } from 'react';
import { Button, Input, Toast, DatePicker, Selector, Radio, Checkbox, TextArea, Stepper, Slider, Switch } from 'antd-mobile';

interface FormField {
    label: string;
    type: 'text' | 'textarea' | 'number' | 'datetime' | 'date' | 'time' | 'file' | 'select' | 'radio' | 'checkbox' | 'switch' | 'slider' | 'stepper';
    name: string;
    value?: any;
    required: boolean;
    editable: boolean;
    options?: { label: string; value: any }[]; // 用于 select、radio、checkbox
    min?: number; // 用于 number、slider、stepper
    max?: number; // 用于 number、slider、stepper
    step?: number; // 用于 slider、stepper
    placeholder?: string; // 用于 input、textarea
    rows?: number; // 用于 textarea
}

interface ApplicationFormProps {
    field: FormField[];
    state: 'noSubmitted' | 'submitted';
    onSubmit?: (formData: Record<string, any>) => void;
    onFormSubmit?: (message: string) => void; // 用于发送用户消息
}

const ApplicationFormComponent: React.FC<ApplicationFormProps> = ({
    field,
    state: initialState,
    onSubmit,
    onFormSubmit
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
            .filter(f => {
                if (!f.required) return false;
                const value = formData[f.name];
                // 对于布尔值，false 也是有效值
                if (typeof value === 'boolean') return false;
                // 对于数字，0 也是有效值
                if (typeof value === 'number') return false;
                return !value;
            })
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

        // 格式化表单数据为 Markdown 格式消息
        const formattedItems = field.map(f => {
            const value = formData[f.name] ?? f.value ?? '';
            let displayValue = '';

            if (Array.isArray(value)) {
                displayValue = value.join(', ');
            } else if (f.type === 'datetime' || f.type === 'date' || f.type === 'time') {
                if (value) {
                    const date = new Date(value);
                    if (f.type === 'datetime') {
                        displayValue = date.toLocaleString('zh-CN');
                    } else if (f.type === 'date') {
                        displayValue = date.toLocaleDateString('zh-CN');
                    } else {
                        displayValue = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
                    }
                }
            } else if (f.type === 'switch') {
                displayValue = value ? '是' : '否';
            } else if (f.type === 'radio' && f.options) {
                const option = f.options.find(opt => opt.value === value);
                displayValue = option ? option.label : String(value);
            } else if (f.type === 'checkbox' && f.options) {
                const selectedLabels = f.options
                    .filter(opt => value.includes(opt.value))
                    .map(opt => opt.label);
                displayValue = selectedLabels.join(', ');
            } else if (f.type === 'file') {
                displayValue = value?.name || '未上传';
            } else {
                displayValue = String(value);
            }

            return `- **${f.label}**: ${displayValue}`;
        }).join('\n');

        // 发送用户消息（使用 Markdown 列表格式）
        if (onFormSubmit) {
            onFormSubmit(`**表单提交**\n\n${formattedItems}`);
        }
    };

    const renderField = (fieldInfo: FormField) => {
        const { label, type, name, required, editable, value: initialValue, options, min, max, step, placeholder, rows } = fieldInfo;
        const value = formData[name] ?? initialValue ?? '';

        // 格式化显示值
        const displayValue = Array.isArray(value) ? value.join(', ') : value;
        const dateValue = type === 'datetime' || type === 'date' || type === 'time' ? (value ? new Date(value) : undefined) : undefined;

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
                    {/* 文本输入框 */}
                    {type === 'text' && (
                        <Input
                            value={displayValue}
                            onChange={(val) => handleFieldChange(name, val)}
                            placeholder={placeholder || `请输入${label}`}
                            disabled={!editable || formState === 'submitted'}
                            className="border border-[var(--color-border)] rounded-lg"
                            style={{ '--font-size': '13px' } as any}
                        />
                    )}

                    {/* 多行文本输入框 */}
                    {type === 'textarea' && (
                        <TextArea
                            value={displayValue}
                            onChange={(val) => handleFieldChange(name, val)}
                            placeholder={placeholder || `请输入${label}`}
                            disabled={!editable || formState === 'submitted'}
                            rows={rows || 3}
                            className="border border-[var(--color-border)] rounded-lg"
                            style={{ '--font-size': '13px' } as any}
                        />
                    )}

                    {/* 数字输入框 */}
                    {type === 'number' && (
                        <Input
                            type="number"
                            value={value}
                            onChange={(val) => handleFieldChange(name, Number(val))}
                            placeholder={placeholder || `请输入${label}`}
                            disabled={!editable || formState === 'submitted'}
                            min={min}
                            max={max}
                            className="border border-[var(--color-border)] rounded-lg"
                            style={{ '--font-size': '13px' } as any}
                        />
                    )}

                    {/* 日期时间选择器 */}
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
                                }) : placeholder || `请选择${label}`}
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

                    {/* 日期选择器 */}
                    {type === 'date' && (
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
                                {dateValue ? dateValue.toLocaleDateString('zh-CN') : placeholder || `请选择${label}`}
                            </div>
                            <DatePicker
                                visible={datePickerVisible === name}
                                onClose={() => setDatePickerVisible(null)}
                                precision="day"
                                onConfirm={(val) => {
                                    handleFieldChange(name, val);
                                    setDatePickerVisible(null);
                                }}
                                value={dateValue}
                            />
                        </>
                    )}

                    {/* 时间选择器 */}
                    {type === 'time' && (
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
                                {dateValue ? dateValue.toLocaleTimeString('zh-CN', {
                                    hour: '2-digit',
                                    minute: '2-digit'
                                }) : placeholder || `请选择${label}`}
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

                    {/* 文件上传 */}
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

                    {/* 下拉选择器 */}
                    {type === 'select' && options && (
                        <Selector
                            options={options}
                            value={Array.isArray(value) ? value : (value ? [value] : [])}
                            onChange={(val) => handleFieldChange(name, val.length > 0 ? val[0] : '')}
                            disabled={!editable || formState === 'submitted'}
                            style={{ '--border-radius': '8px', '--checked-color': '#1677ff' } as any}
                        />
                    )}

                    {/* 单选框 */}
                    {type === 'radio' && options && (
                        <Radio.Group
                            value={value}
                            onChange={(val) => handleFieldChange(name, val)}
                            disabled={!editable || formState === 'submitted'}
                        >
                            <div className="flex flex-row flex-wrap gap-3">
                                {options.map(opt => (
                                    <Radio key={opt.value} value={opt.value} style={{ '--icon-size': '18px', '--font-size': '13px' } as any}>
                                        {opt.label}
                                    </Radio>
                                ))}
                            </div>
                        </Radio.Group>
                    )}

                    {/* 多选框 */}
                    {type === 'checkbox' && options && (
                        <Checkbox.Group
                            value={Array.isArray(value) ? value : []}
                            onChange={(val) => handleFieldChange(name, val)}
                            disabled={!editable || formState === 'submitted'}
                        >
                            <div className="flex flex-row flex-wrap gap-3">
                                {options.map(opt => (
                                    <Checkbox key={opt.value} value={opt.value} style={{ '--icon-size': '18px', '--font-size': '13px' } as any}>
                                        {opt.label}
                                    </Checkbox>
                                ))}
                            </div>
                        </Checkbox.Group>
                    )}

                    {/* 开关 */}
                    {type === 'switch' && (
                        <Switch
                            checked={Boolean(value)}
                            onChange={(val) => handleFieldChange(name, val)}
                            disabled={!editable || formState === 'submitted'}
                            style={{ '--checked-color': '#1677ff' } as any}
                        />
                    )}

                    {/* 滑块 */}
                    {type === 'slider' && (
                        <div className="pt-2">
                            <Slider
                                value={Number(value) || min || 0}
                                onChange={(val) => handleFieldChange(name, val)}
                                disabled={!editable || formState === 'submitted'}
                                min={min || 0}
                                max={max || 100}
                                step={step || 1}
                                style={{ '--fill-color': '#1677ff' } as any}
                            />
                            <div className="text-xs text-[var(--color-text-3)] text-right mt-1">
                                当前值: {value || min || 0}
                            </div>
                        </div>
                    )}

                    {/* 步进器 */}
                    {type === 'stepper' && (
                        <Stepper
                            value={Number(value) || min || 0}
                            onChange={(val) => handleFieldChange(name, val)}
                            disabled={!editable || formState === 'submitted'}
                            min={min || 0}
                            max={max || 100}
                            step={step || 1}
                            style={{ '--border-radius': '8px' } as any}
                        />
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
                            style={
                                {
                                    '--adm-font-size-9': '15px'
                                } as React.CSSProperties}
                        >
                            提交
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
