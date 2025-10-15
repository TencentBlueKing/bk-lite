'use client';
import React, {
  useState,
  useCallback,
  useMemo,
  useEffect,
  useRef,
} from 'react';
import { AutoComplete, Input } from 'antd';
import { DefaultOptionType } from 'antd/es/select';
import { debounce } from 'lodash';
import useIntegrationApi from '@/app/log/api/integration';
import { useTranslation } from '@/utils/i18n';

// 字段值数据结构
interface FieldValueItem {
  value: string;
  hits: number;
}

export interface SmartSearchInputProps {
  value?: string;
  onChange?: (value: string) => void;
  onPressEnter?: () => void;
  placeholder?: string;
  className?: string;
  fields?: string[]; // 字段名列表
  getTimeRange?: () => number[]; // 获取时间范围的方法
  addonAfter?: React.ReactNode;
  disabled?: boolean;
}

const SmartSearchInput: React.FC<SmartSearchInputProps> = React.memo(
  ({
    value = '',
    onChange,
    onPressEnter,
    placeholder,
    className,
    fields = [],
    getTimeRange,
    addonAfter,
    disabled = false,
  }) => {
    const { t } = useTranslation();
    const [options, setOptions] = useState<DefaultOptionType[]>([]);
    const [loading, setLoading] = useState(false);
    const [dropdownOpen, setDropdownOpen] = useState(false);

    // 设置默认的 placeholder
    const defaultPlaceholder =
      placeholder || t('log.search.smartSearchPlaceHolder');

    // 当前字段的值列表（不缓存，每次重新获取）
    const [currentFieldValues, setCurrentFieldValues] = useState<
      FieldValueItem[]
    >([]);
    const [currentFieldName, setCurrentFieldName] = useState<string>('');

    // 添加已请求过的字段缓存，避免重复请求空结果
    const [requestedFields, setRequestedFields] = useState<Set<string>>(
      new Set()
    );

    // 添加防护标志，防止循环更新
    const isUpdatingRef = useRef(false);
    const lastValueRef = useRef(value);
    const lastRequestKeyRef = useRef<string>('');
    const lastContextRef = useRef<any>(null);

    // 使用 API hook
    const { getFieldValues } = useIntegrationApi();

    // 解析当前光标位置的上下文 - 直接使用传入的光标位置
    const parseContextRef = useRef((inputValue: string, cursorPos?: number) => {
      const pos = cursorPos ?? inputValue.length;

      // 找到光标前最近的空格和光标后最近的空格
      let segmentStart = 0;
      let segmentEnd = inputValue.length;

      // 向前找空格
      for (let i = pos - 1; i >= 0; i--) {
        if (inputValue[i] === ' ') {
          segmentStart = i + 1;
          break;
        }
      }

      // 向后找空格
      for (let i = pos; i < inputValue.length; i++) {
        if (inputValue[i] === ' ') {
          segmentEnd = i;
          break;
        }
      }

      const currentSegment = inputValue.slice(segmentStart, segmentEnd);
      const posInSegment = pos - segmentStart;
      const colonIndex = currentSegment.indexOf(':');

      if (colonIndex === -1) {
        // 没有冒号，字段名输入
        const prefix = currentSegment.slice(0, posInSegment);
        return {
          type: 'field',
          prefix,
          fieldName: '',
          isAfterColon: false,
          startPos: segmentStart,
          endPos: segmentEnd,
          currentSegment,
          hasExistingValue: false,
        };
      }

      // 有冒号
      const fieldName = currentSegment.slice(0, colonIndex);
      const valueAfterColon = currentSegment.slice(colonIndex + 1);

      if (posInSegment <= colonIndex) {
        // 光标在冒号前，字段名编辑
        const prefix = currentSegment.slice(0, posInSegment);
        return {
          type: 'field',
          prefix,
          fieldName: '',
          isAfterColon: false,
          startPos: segmentStart,
          endPos: segmentStart + colonIndex,
          currentSegment,
          hasExistingValue: false,
        };
      }

      // 光标在冒号后，字段值编辑
      const valuePrefix = valueAfterColon.slice(
        0,
        posInSegment - colonIndex - 1
      );
      const hasExistingValue = valueAfterColon.length > 0;

      return {
        type: 'value',
        prefix: valuePrefix,
        fieldName,
        isAfterColon: true,
        startPos: segmentStart + colonIndex + 1,
        endPos: segmentEnd,
        currentSegment,
        hasExistingValue,
      };
    });

    const parseContext = parseContextRef.current;

    // 获取字段值 - 使用 useRef 保持稳定引用
    const getFieldValuesFromAPI = useRef(
      async (fieldName: string): Promise<FieldValueItem[]> => {
        if (!getFieldValues) return [];

        try {
          setLoading(true);

          // 获取时间范围
          const times = getTimeRange?.() || [];

          const params = {
            filed: fieldName,
            start_time: times[0] ? new Date(times[0]).toISOString() : '',
            end_time: times[1] ? new Date(times[1]).toISOString() : '',
            limit: 50,
          };

          const values = await getFieldValues(params);
          return values?.values || [];
        } catch (error) {
          console.error('Failed to fetch field values:', error);
          return [];
        } finally {
          setLoading(false);
        }
      }
    );

    // 更新 getFieldValuesFromAPI 的引用
    useEffect(() => {
      getFieldValuesFromAPI.current = async (
        fieldName: string
      ): Promise<FieldValueItem[]> => {
        if (!getFieldValues) return [];

        try {
          setLoading(true);

          // 获取时间范围
          const times = getTimeRange?.() || [];

          const params = {
            filed: fieldName,
            start_time: times[0] ? new Date(times[0]).toISOString() : '',
            end_time: times[1] ? new Date(times[1]).toISOString() : '',
            limit: 50,
          };

          const values = await getFieldValues(params);
          return values?.values || [];
        } catch (error) {
          console.error('Failed to fetch field values:', error);
          return [];
        } finally {
          setLoading(false);
        }
      };
    }, [getFieldValues, getTimeRange]);

    // 获取字段值的防抖函数 - 每次都重新获取，但避免重复请求空结果
    const debouncedGetFieldValues = useRef(
      debounce(async (fieldName: string) => {
        // 避免重复请求同样的字段
        if (loading && lastRequestKeyRef.current === fieldName) {
          return;
        }

        // 检查是否已经请求过该字段且返回为空，如果是则不再请求
        if (
          requestedFields.has(fieldName) &&
          currentFieldName === fieldName &&
          currentFieldValues.length === 0
        ) {
          return;
        }

        lastRequestKeyRef.current = fieldName;

        // 先清空当前值列表
        setCurrentFieldValues([]);
        setCurrentFieldName(fieldName);

        // 显示加载状态并强制打开下拉列表
        setDropdownOpen(true);
        setOptions([
          {
            value: 'loading',
            label: (
              <div className="flex items-center justify-center text-gray-400">
                <span>{t('log.search.loadingEllipsis')}</span>
              </div>
            ),
            disabled: true,
          },
        ]);

        const values = await getFieldValuesFromAPI.current(fieldName);

        // 标记该字段已被请求过
        setRequestedFields((prev) => new Set(prev).add(fieldName));

        // 如果没有获取到值列表，关闭下拉列表
        if (!values || values.length === 0) {
          setCurrentFieldValues([]);
          setOptions([]);
          setDropdownOpen(false);
          return;
        }

        // 设置当前字段的值列表
        setCurrentFieldValues(values);

        // 生成选项并显示
        generateValueOptions(values, '');
      }, 300)
    );

    // 生成值选项的函数 - 支持本地筛选
    const generateValueOptions = useCallback(
      (values: FieldValueItem[], prefix: string) => {
        if (!values || values.length === 0) {
          setOptions([]);
          setDropdownOpen(false);
          return;
        }

        // 智能过滤：支持多种匹配方式
        const filteredValues = values.filter((item) => {
          if (prefix === '') return true; // 没有输入前缀时显示所有值

          const lowerVal = item.value.toLowerCase();
          const lowerPrefix = prefix.toLowerCase();

          // 支持多种匹配模式：
          // 1. 开头匹配（优先级最高）
          // 2. 包含匹配
          // 3. 分词匹配（用空格分隔的词）
          return (
            lowerVal.startsWith(lowerPrefix) ||
            lowerVal.includes(lowerPrefix) ||
            lowerVal.split(/\s+/).some((word) => word.startsWith(lowerPrefix))
          );
        });

        // 按匹配优先级排序
        filteredValues.sort((a, b) => {
          const lowerA = a.value.toLowerCase();
          const lowerB = b.value.toLowerCase();
          const lowerPrefix = prefix.toLowerCase();

          // 开头匹配的排在前面
          const aStartsWith = lowerA.startsWith(lowerPrefix);
          const bStartsWith = lowerB.startsWith(lowerPrefix);

          if (aStartsWith && !bStartsWith) return -1;
          if (!aStartsWith && bStartsWith) return 1;

          // 按照 hits 数量降序排列（热门的排在前面）
          if (b.hits !== a.hits) return b.hits - a.hits;

          // 最后按长度排序（更精确的匹配优先）
          return a.value.length - b.value.length;
        });

        // 如果没有匹配的值，显示"无匹配项"提示
        if (filteredValues.length === 0) {
          setOptions([
            {
              value: 'no-match',
              label: (
                <div className="flex items-center justify-center text-gray-400">
                  <span>{t('log.search.noMatchValues')}</span>
                </div>
              ),
              disabled: true,
            },
          ]);
          setDropdownOpen(true);
          return;
        }

        const valueOptions: DefaultOptionType[] = filteredValues.map((item) => {
          return {
            value: item.value,
            label: (
              <div className="flex items-center justify-between">
                <span className="mr-[10px]">{item.value}</span>
                <span className="text-gray-400 text-xs">{item.hits} hits</span>
              </div>
            ),
            type: 'value',
          };
        });

        setOptions(valueOptions);
        setDropdownOpen(true);
      },
      []
    );

    // 同步外部 value 变化
    useEffect(() => {
      if (!isUpdatingRef.current && value !== lastValueRef.current) {
        lastValueRef.current = value;
      }
    }, [value]);

    // 清理防抖函数
    useEffect(() => {
      return () => {
        debouncedGetFieldValues.current.cancel();
      };
    }, []);

    // 生成补全选项 - 使用 useCallback 优化
    const generateOptions = useCallback(
      async (inputValue: string, cursorPos?: number) => {
        const context = parseContext(inputValue, cursorPos);
        const { type, prefix, fieldName } = context;

        if (type === 'field') {
          // 字段名补全 - 需要至少输入1个字符
          if (!prefix || prefix.length === 0) {
            setOptions([]);
            setDropdownOpen(false);
            return;
          }

          const filteredFields = fields.filter((field) =>
            field.toLowerCase().includes(prefix.toLowerCase())
          );

          // 如果没有匹配的字段，不显示下拉列表
          if (filteredFields.length === 0) {
            setOptions([]);
            setDropdownOpen(false);
            return;
          }

          const fieldOptions: DefaultOptionType[] = filteredFields.map(
            (field) => ({
              value: field,
              label: (
                <div className="flex items-center justify-between">
                  <span>{field}</span>
                  <span className="text-gray-400 text-xs">
                    {t('log.search.field')}
                  </span>
                </div>
              ),
              type: 'field',
            })
          );

          setOptions(fieldOptions);
          setDropdownOpen(true);
        } else if (type === 'value' && fieldName) {
          // 字段值补全 - 只有当字段名在字段列表中存在时才进行补全
          const isValidField = fields.includes(fieldName);
          if (isValidField) {
            // 如果当前字段有值列表且字段名匹配，直接进行本地筛选
            if (
              currentFieldValues.length > 0 &&
              currentFieldName === fieldName
            ) {
              generateValueOptions(currentFieldValues, prefix);
            } else {
              // 检查是否已经请求过该字段且为空
              if (
                requestedFields.has(fieldName) &&
                currentFieldName === fieldName &&
                currentFieldValues.length === 0
              ) {
                // 已经请求过且为空，不显示任何选项
                setOptions([]);
                setDropdownOpen(false);
                return;
              }

              // 如果没有值列表，显示加载提示
              setOptions([
                {
                  value: 'loading',
                  label: (
                    <div className="flex items-center justify-center text-gray-400">
                      <span>{t('log.search.loadingEllipsis')}</span>
                    </div>
                  ),
                  disabled: true,
                },
              ]);
              setDropdownOpen(true);

              // 发起请求获取字段值
              debouncedGetFieldValues.current(fieldName);
            }
          } else {
            setOptions([]);
            setDropdownOpen(false);
          }
        } else {
          setOptions([]);
          setDropdownOpen(false);
        }
      },
      [
        fields,
        currentFieldValues,
        currentFieldName,
        generateValueOptions,
        requestedFields,
      ] // 添加 requestedFields 依赖
    );

    // 保存真实光标位置的 ref
    const realCursorPosRef = useRef<number>(0);

    // 统一的输入处理函数 - 重新设计逻辑
    const handleInputChange = useCallback(
      (newValue: string) => {
        isUpdatingRef.current = true;
        lastValueRef.current = newValue;

        try {
          // 更新父组件的值
          onChange?.(newValue);

          // 如果以空格结尾，清空选项
          if (/\s$/.test(newValue)) {
            setOptions([]);
            setDropdownOpen(false);
            return;
          }

          // 使用保存的真实光标位置
          const cursorPos = realCursorPosRef.current;

          // 获取当前输入上下文
          const currentContext = parseContext(newValue, cursorPos);

          // 检测是否刚输入了冒号
          const lastChar = newValue.slice(-1);
          if (lastChar === ':') {
            // 刚输入冒号，检查是否为有效字段
            const beforeColon = newValue.slice(0, -1);
            const context = parseContext(beforeColon, cursorPos - 1);

            if (
              context.type === 'field' &&
              context.prefix &&
              fields.includes(context.prefix)
            ) {
              // 有效字段，准备获取值列表
              requestAnimationFrame(() => {
                setDropdownOpen(true);
                setCurrentFieldValues([]);
                setCurrentFieldName('');
                debouncedGetFieldValues.current.cancel();
                debouncedGetFieldValues.current(context.prefix);
              });
            }
            return;
          }

          // 正常输入处理
          if (currentContext.type === 'field') {
            // 字段名输入
            generateOptions(newValue, cursorPos);
          } else if (
            currentContext.type === 'value' &&
            currentContext.fieldName &&
            fields.includes(currentContext.fieldName)
          ) {
            // 值输入 - 核心逻辑

            // 检查是否有该字段的缓存值列表
            if (
              currentFieldValues.length > 0 &&
              currentFieldName === currentContext.fieldName
            ) {
              // 有缓存值，直接进行本地过滤
              generateValueOptions(currentFieldValues, currentContext.prefix);
            } else if (currentContext.hasExistingValue) {
              // 字段已有值但没有缓存值列表，不发送请求
              // 这种情况下用户只是在编辑现有值，不需要补全
              setOptions([]);
              setDropdownOpen(false);
            } else {
              // 字段没有值，且没有缓存，可以发送请求
              if (
                !(
                  requestedFields.has(currentContext.fieldName) &&
                  currentFieldName === currentContext.fieldName &&
                  currentFieldValues.length === 0
                )
              ) {
                // 显示加载并发送请求
                setOptions([
                  {
                    value: 'loading',
                    label: (
                      <div className="flex items-center justify-center text-gray-400">
                        <span>{t('log.search.loadingEllipsis')}</span>
                      </div>
                    ),
                    disabled: true,
                  },
                ]);
                setDropdownOpen(true);
                debouncedGetFieldValues.current(currentContext.fieldName);
              } else {
                console.log(
                  'Already requested and empty, not requesting again'
                );
                // 已请求过且为空
                setOptions([]);
                setDropdownOpen(false);
              }
            }
          } else {
            console.log('Other case, clearing options');
            // 其他情况
            setOptions([]);
            setDropdownOpen(false);
          }

          lastContextRef.current = currentContext;
        } finally {
          setTimeout(() => {
            isUpdatingRef.current = false;
          }, 0);
        }
      },
      [
        onChange,
        generateOptions,
        fields,
        currentFieldValues,
        currentFieldName,
        parseContext,
        requestedFields,
      ]
    );

    // 处理选项选择
    const handleSelect = useCallback(
      (selectedValue: string, option: DefaultOptionType) => {
        try {
          // 使用真实的光标位置解析上下文
          const context = parseContext(value, realCursorPosRef.current);

          let newValue = value;

          if (option.type === 'field') {
            // 选择字段名，替换当前字段并自动添加冒号
            const beforeSelection = value.slice(0, context.startPos);
            const afterSelection = value.slice(context.endPos);

            // 检查是否需要添加冒号：如果替换后的位置紧跟着冒号，则不添加
            const needsColon = !afterSelection.startsWith(':');
            const colonSuffix = needsColon ? ':' : '';

            newValue = `${beforeSelection}${selectedValue}${colonSuffix}${afterSelection}`;

            // 更新值
            lastValueRef.current = newValue;
            onChange?.(newValue);

            // 使用 requestAnimationFrame 确保状态更新顺序
            requestAnimationFrame(() => {
              // 计算新的光标位置（字段名后，冒号后）
              const newCursorPos =
                context.startPos + selectedValue.length + (needsColon ? 1 : 0);

              // 更新真实光标位置的引用
              realCursorPosRef.current = newCursorPos;

              // 设置实际的光标位置
              const input = document.querySelector('input');
              if (input) {
                setTimeout(() => {
                  input.setSelectionRange(newCursorPos, newCursorPos);
                  realCursorPosRef.current = newCursorPos;
                }, 0);
              }

              // 解析新的上下文，确保能正确识别为字段值模式
              const newContext = parseContext(newValue, newCursorPos);

              if (newContext.type === 'value' && newContext.fieldName) {
                // 显示值选项，而不是字段选项
                setDropdownOpen(true);
                // 清空当前值列表，重新获取
                setCurrentFieldValues([]);
                setCurrentFieldName('');
                // 直接调用防抖函数获取字段值
                debouncedGetFieldValues.current(newContext.fieldName);
              } else {
                setOptions([]);
                setDropdownOpen(false);
              }
            });
          } else if (option.type === 'value') {
            // 选择字段值，只替换当前字段的值部分
            const beforeSelection = value.slice(0, context.startPos);
            const afterSelection = value.slice(context.endPos);
            newValue = `${beforeSelection}${selectedValue}${afterSelection}`;

            lastValueRef.current = newValue;
            onChange?.(newValue);
            setOptions([]);
            setDropdownOpen(false);
          }
        } finally {
          setTimeout(() => {
            isUpdatingRef.current = false;
          }, 0);
        }
      },
      [value, onChange, parseContext]
    );

    // 处理键盘事件，确保Enter键总是执行搜索而不是选择选项
    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.stopPropagation();
          setOptions([]);
          setDropdownOpen(false);
          onPressEnter?.();
        }
      },
      [onPressEnter]
    );

    // 自定义输入框组件，捕获真实光标位置
    const customInput = useMemo(
      () => (
        <Input
          placeholder={defaultPlaceholder}
          onKeyDown={handleKeyDown}
          addonAfter={addonAfter}
          disabled={disabled}
          onInput={(e: React.FormEvent<HTMLInputElement>) => {
            // 捕获真实的光标位置
            const input = e.target as HTMLInputElement;
            realCursorPosRef.current = input.selectionStart || 0;
          }}
          onSelect={(e: React.SyntheticEvent<HTMLInputElement>) => {
            // 也在选择事件中更新光标位置
            const input = e.target as HTMLInputElement;
            realCursorPosRef.current = input.selectionStart || 0;
          }}
          onClick={(e: React.MouseEvent<HTMLInputElement>) => {
            // 点击时也更新光标位置
            const input = e.target as HTMLInputElement;
            setTimeout(() => {
              realCursorPosRef.current = input.selectionStart || 0;
            }, 0);
          }}
        />
      ),
      [defaultPlaceholder, handleKeyDown, addonAfter, disabled]
    );

    return (
      <AutoComplete
        className={className}
        value={value}
        options={options}
        onSelect={handleSelect}
        onChange={handleInputChange} // 只使用一个统一的处理函数
        open={dropdownOpen && options.length > 0} // 只有在有选项时才显示下拉
        onDropdownVisibleChange={setDropdownOpen} // 同步下拉状态
        notFoundContent={loading ? t('log.search.loadingEllipsis') : ''}
        filterOption={false} // 禁用默认过滤，使用自定义逻辑
        dropdownMatchSelectWidth={false}
        dropdownStyle={{ minWidth: 300 }}
      >
        {customInput}
      </AutoComplete>
    );
  },
  (prevProps, nextProps) => {
    // 自定义比较函数，避免不必要的重新渲染
    return (
      prevProps.value === nextProps.value &&
      prevProps.placeholder === nextProps.placeholder &&
      prevProps.className === nextProps.className &&
      prevProps.disabled === nextProps.disabled &&
      prevProps.onChange === nextProps.onChange &&
      prevProps.onPressEnter === nextProps.onPressEnter &&
      prevProps.getTimeRange === nextProps.getTimeRange &&
      JSON.stringify(prevProps.fields) === JSON.stringify(nextProps.fields)
    );
  }
);

SmartSearchInput.displayName = 'SmartSearchInput';
export default SmartSearchInput;
