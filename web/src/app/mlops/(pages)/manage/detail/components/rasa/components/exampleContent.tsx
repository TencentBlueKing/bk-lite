import { Tree, Dropdown, Menu, Button, Input, Spin, message, Table, Form, Popconfirm, Select, Switch } from "antd";
import { Key, useState, useMemo, useCallback, useRef, useEffect } from "react";
import PermissionWrapper from '@/components/permission';
import { MoreOutlined, PlusOutlined, LeftOutlined, RightOutlined } from "@ant-design/icons";
import { useTranslation } from "@/utils/i18n";
import StoryFlow from "./StoryFlow";
import contentStyle from './index.module.scss';
import EntitySelectModal from "@/app/mlops/hooks/manage/entitySelectModal";
import useMlopsManageApi from "@/app/mlops/api/manage";

// 专门为 EntitySelectModal 定义的 ref 接口
interface EntityModalRef {
  showModal: () => void;
}

// Response 数据类型接口
interface ResponseItem {
  type: 'text' | 'button';
  value: string;
  payloads?: { title: string; payload: string }[];
  // 保持向后兼容
  payload?: string;
}

interface IntentTreeProps {
  menu: string;
  dataset: string;
  data: any[];
  loading: boolean;
  handleAdd: () => void;
  handleEdit: (record: any) => void;
  handleDel: (id: number) => void;
  onSuccess: () => void;
}

const SUPPORTED_ITEMS = ['intent', 'response', 'story'] as const;

// Payload 选项配置
const PAYLOAD_OPTIONS = [
  { label: 'Affirm', value: '/affirm' },
  { label: 'Deny', value: '/deny' },
];

const ExampleContent = ({ menu, data, dataset, loading, handleAdd, handleEdit, handleDel, onSuccess }: IntentTreeProps) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const { updateRasaIntentFile, updateRasaResponseFile } = useMlopsManageApi();
  const [selectKey, setSelectKey] = useState<Key[]>([]);
  const [searchValue, setSearchValue] = useState<string>('');
  const [exampleData, setExampleData] = useState<any[]>([]);
  const [editingKey, setEditingKey] = useState<string>('');
  const [originalData, setOriginalData] = useState<any>(null);
  const [showTree, setShowTree] = useState<boolean>(true);
  const selectedTextRef = useRef<any>(null);
  const entityModalRef = useRef<EntityModalRef>(null);

  const supportedItems = useMemo(() => SUPPORTED_ITEMS, []);

  const getExamplesByMenu = useCallback((menu: string, selectedData: any): any[] => {
    if (supportedItems.includes(menu as any)) {
      const examples = selectedData?.example || [];

      if (menu === 'response') {
        // Response 类型：处理新的对象格式数据
        return examples.map((example: string | ResponseItem, index: number) => {
          if (typeof example === 'string') {
            // 兼容旧格式：字符串类型
            return {
              key: `example_${index}`,
              id: index,
              type: 'text',
              value: example,
              text: example // 保持向后兼容
            };
          } else if (example && typeof example === 'object') {
            // 新格式：对象类型
            return {
              key: `example_${index}`,
              id: index,
              type: example.type || 'text',
              value: example.value || '',
              payloads: example.payloads || (example.payload ? [{ title: 'Action', payload: example.payload }] : undefined),
              payload: example.payload, // 保持向后兼容
              text: example.value || '' // 为表格显示提供统一的 text 字段
            };
          }
          return {
            key: `example_${index}`,
            id: index,
            type: 'text',
            value: '',
            text: ''
          };
        });
      } else {
        // Intent 类型：保持原有的字符串格式
        return examples.map((example: string, index: number) => ({
          key: `example_${index}`,
          id: index,
          text: example
        }));
      }
    }
    return [];
  }, [supportedItems]);

  const filterTreeData = useCallback((data: any[], searchValue: string) => {
    if (!searchValue.trim()) return data;
    const searchTerm = searchValue.toLowerCase().trim();

    return data.filter((item: any) => {
      const itemName = item?.name?.toLowerCase() || '';

      return itemName.includes(searchTerm) ||
        searchTerm.split('').every(char => itemName.includes(char));
    });
  }, []);

  const treeData = useMemo(() => {
    const rawData = data?.map((item: any, index: number) => ({
      key: `${menu}_${item?.id || index}`,
      name: item?.name,
      title: item,
      ...item
    })) || [];

    return filterTreeData(rawData, searchValue);
  }, [data, menu, searchValue, filterTreeData]);

  const currentExampleData = useMemo(() => {
    if (!selectKey.length) return [];

    const [key] = selectKey;
    const id = treeData.find((item: any) => item.key === key)?.id;
    const selectedData = data?.find((item: any) => item?.id === id);

    return getExamplesByMenu(menu, selectedData);
  }, [selectKey, treeData, data, menu, getExamplesByMenu]);

  useEffect(() => {
    setExampleData(currentExampleData);
  }, [currentExampleData]);

  // 当选择项变化时，取消编辑状态
  useEffect(() => {
    setEditingKey('');
    setOriginalData(null);
    form.resetFields();
  }, [selectKey, form]);

  // 处理表格内文字选中（用于实体标记）
  const handleTextSelection = useCallback((inputElement: HTMLInputElement) => {
    if (menu !== 'intent') return;

    const start = inputElement.selectionStart;
    const end = inputElement.selectionEnd;

    if (start !== null && end !== null && start !== end) {
      const text = inputElement.value.substring(start, end);

      if (text.trim()) {
        const textInfo = {
          text: text.trim(),
          start,
          end,
          fullInputValue: inputElement.value,
          inputElement
        };
        selectedTextRef.current = textInfo;

        // 使用实体选择模态框
        if (entityModalRef.current) {
          entityModalRef.current.showModal();
        }
      }
    }
  }, [menu]);

  // 处理实体选择
  const handleEntitySelect = useCallback((entityName: string) => {
    const currentSelectedText = selectedTextRef.current;
    if (currentSelectedText) {
      const { text, start, end, fullInputValue } = currentSelectedText;

      const newValue =
        fullInputValue.substring(0, start) +
        `[${text}](${entityName})` +
        fullInputValue.substring(end);

      // 更新form中的值
      const record = form.getFieldsValue();
      form.setFieldsValue({
        ...record,
        text: newValue
      });

      selectedTextRef.current = null;
    }
  }, [form]);

  // 保存样例数据
  const handleSaveExamples = useCallback(async () => {
    if (!selectKey.length) return;

    const [key] = selectKey;
    const id = treeData.find((item: any) => item.key === key)?.id;
    const selectedData = data?.find((item: any) => item?.id === id);

    if (selectedData) {
      let examples;

      if (menu === 'response') {
        // Response 类型：转换为新的对象格式
        examples = exampleData
          .filter((item: any) => item.text?.trim() || item.value?.trim())
          .map((item: any) => ({
            type: item.type || 'text',
            value: item.value || item.text || '',
            ...(item.type === 'button' && item.payloads?.length ? { payloads: item.payloads } : {}),
            // 向后兼容：如果有单个 payload，也保存
            ...(item.type === 'button' && item.payload && !item.payloads?.length ? { payload: item.payload } : {})
          }));
      } else {
        // Intent 类型：保持字符串格式
        examples = exampleData
          .map((item: any) => item.text)
          .filter((text: string) => text?.trim());
      }

      try {
        if (menu === 'intent') {
          await updateRasaIntentFile(id, { example: examples });
        } else if (menu === 'response') {
          await updateRasaResponseFile(id, { example: examples });
        }
        message.success(t(`common.updateSuccess`));
        onSuccess();
      } catch (e) {
        console.log(e);
        message.error(t(`common.updateFailed`));
      }
    }
  }, [selectKey, treeData, data, exampleData, menu, updateRasaIntentFile, updateRasaResponseFile, t, onSuccess]);

  // 表格编辑相关函数
  const isEditing = (record: any) => record?.key === editingKey;

  const edit = (record: any) => {
    if (!record || !record.key) {
      console.warn('Edit called with invalid record:', record);
      return;
    }
    // 保存编辑前的原始数据
    setOriginalData({ ...record });
    form.setFieldsValue({ text: '', ...record });
    setEditingKey(record.key);
  };

  const cancel = () => {
    // 恢复原始数据
    if (originalData && editingKey) {
      setExampleData(prevData => {
        const newData = [...prevData];
        const index = newData.findIndex(item => item.key === editingKey);
        if (index > -1) {
          newData[index] = { ...originalData };
        }
        return newData;
      });
    }
    setEditingKey('');
    setOriginalData(null);
    form.resetFields();
  };

  const save = async (key: string) => {
    if (!key) {
      console.warn('Save called with invalid key:', key);
      return;
    }
    try {
      const row = await form.validateFields();
      const newData = [...exampleData];
      const index = newData.findIndex((item) => key === item.key);

      if (index > -1) {
        const item = newData[index];
        newData.splice(index, 1, { ...item, ...row });
        setExampleData(newData);
        setEditingKey('');
        setOriginalData(null); // 清除原始数据
      } else {
        newData.push({ ...row, key, id: exampleData.length });
        setExampleData(newData);
        setEditingKey('');
        setOriginalData(null); // 清除原始数据
      }
    } catch (errInfo) {
      console.log('Validate Failed:', errInfo);
    }
  };

  const deleteExample = (key: string) => {
    if (!key) {
      console.warn('Delete called with invalid key:', key);
      return;
    }
    const newData = exampleData.filter((item) => item.key !== key);
    setExampleData(newData);
    // 如果删除的是正在编辑的行，清除编辑状态
    if (editingKey === key) {
      setEditingKey('');
      setOriginalData(null);
      form.resetFields();
    }
  };

  // 可编辑单元格组件
  const EditableCell = ({
    editing,
    dataIndex,
    record,
    children,
    ...restProps
  }: any) => {
    // 如果没有 dataIndex，说明是操作列，直接渲染子元素
    if (!dataIndex) {
      return <td {...restProps}>{children}</td>;
    }

    // Response 类型的输入组件
    if (menu === 'response' && dataIndex === 'text') {
      const inputNode = (
        <div className="flex gap-2 items-center">
          <Input
            className="!w-[300px]"
            style={{ flex: 1 }}
            placeholder={t(`datasets.editEaxmpleTip`)}
            value={record?.value || record?.text || ''}
            onChange={(e) => {
              // 直接更新 exampleData 中的值
              setExampleData(prevData => {
                const newData = [...prevData];
                const index = newData.findIndex(item => item.key === record.key);
                if (index > -1) {
                  newData[index] = {
                    ...newData[index],
                    value: e.target.value,
                    text: e.target.value
                  };
                }
                return newData;
              });
            }}
          />
          {/* Switch 按钮控制类型 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">按钮</span>
            <Switch
              size="small"
              checked={record?.type === 'button'}
              onChange={(checked) => {
                setExampleData(prevData => {
                  const newData = [...prevData];
                  const index = newData.findIndex(item => item.key === record.key);
                  if (index > -1) {
                    const newType = checked ? 'button' : 'text';
                    newData[index] = {
                      ...newData[index],
                      type: newType,
                      ...(newType === 'button' ? {
                        payloads: [{ title: PAYLOAD_OPTIONS[0].label, payload: PAYLOAD_OPTIONS[0].value }],
                        payload: PAYLOAD_OPTIONS[0].value // 保持向后兼容
                      } : {
                        payloads: undefined,
                        payload: undefined
                      })
                    };
                  }
                  return newData;
                });
              }}
            />
          </div>
          {record?.type === 'button' && (
            <Select
              mode="multiple"
              className="!w-[200px] h-[30px]"
              placeholder="选择按钮动作"
              value={record?.payloads?.map((p: any) => p.payload) || (record?.payload ? [record.payload] : [])}
              onChange={(selectedValues: string[]) => {
                const payloads = selectedValues.map(value => ({
                  title: PAYLOAD_OPTIONS.find(opt => opt.value === value)?.label || value.replace('/', ''),
                  payload: value
                }));

                setExampleData(prevData => {
                  const newData = [...prevData];
                  const index = newData.findIndex(item => item.key === record.key);
                  if (index > -1) {
                    newData[index] = {
                      ...newData[index],
                      payloads: payloads,
                      payload: selectedValues[0] || '/affirm' // 保持向后兼容
                    };
                  }
                  return newData;
                });
              }}
              options={PAYLOAD_OPTIONS}
              maxTagCount={2}
              maxTagTextLength={8}
            />
          )}
        </div>
      );

      return (
        <td {...restProps}>
          {editing ? (
            <Form.Item
              name={dataIndex}
              style={{ margin: 0 }}
              rules={[
                {
                  required: true,
                  message: t(`common.inputMsg`),
                },
              ]}
            >
              {inputNode}
            </Form.Item>
          ) : (
            <div
              className="min-h-[24px] flex items-center cursor-pointer hover:bg-gray-50 px-2 py-1"
              onClick={() => {
                if (record && record.key) {
                  edit(record);
                }
              }}
            >
              <span className="flex-1">{record?.value || record?.text || ''}</span>
              {record?.type === 'button' && (
                <div className="flex flex-wrap gap-1 ml-2">
                  {record?.payloads?.length > 0 ? (
                    record.payloads.map((p: any, idx: number) => (
                      <span
                        key={idx}
                        className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200"
                      >
                        {p.title || p.payload.replace('/', '')}
                      </span>
                    ))
                  ) : record?.payload ? (
                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
                      {PAYLOAD_OPTIONS.find(opt => opt.value === record.payload)?.label || record.payload.replace('/', '')}
                    </span>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </td>
      );
    }

    // Intent 类型的输入组件（保持原有逻辑）
    const inputNode = (
      <Input
        onMouseUp={(e) => handleTextSelection(e.target as HTMLInputElement)}
        onKeyUp={(e) => handleTextSelection(e.target as HTMLInputElement)}
        placeholder={t(`datasets.editEaxmpleTip`)}
      />
    );

    return (
      <td {...restProps}>
        {editing ? (
          <Form.Item
            name={dataIndex}
            style={{ margin: 0 }}
            rules={[
              {
                required: true,
                message: t(`common.inputMsg`),
              },
            ]}
          >
            {inputNode}
          </Form.Item>
        ) : (
          <div
            className="min-h-[24px] flex items-center cursor-pointer hover:bg-gray-50 px-2 py-1"
            onClick={() => {
              if (record && record.key) {
                edit(record);
              }
            }}
          >
            {menu === 'intent' ? renderHighlightedText(record?.text || '') : (record?.text || '')}
          </div>
        )}
      </td>
    );
  };

  // 获取表格列配置
  const getColumns = () => {
    const columns = [
      {
        title: t(`datasets.example`),
        dataIndex: 'text',
        // align: 'center',
        editable: true,
        render: (text: string, record: any) => {

          if (menu === 'response') {
            // Response 类型：显示 value 和 type 信息
            return (
              <div className="flex items-center justify-between">
                <span className="flex-1">{record?.value || record?.text || ''}</span>
                <div className="flex items-center gap-2">
                  {/* 类型标签显示 */}
                  <span className={`text-xs px-2 py-1 rounded ${record?.type === 'button'
                    ? 'bg-green-100 text-green-600'
                    : 'bg-blue-100 text-blue-600'
                  }`}>
                    {record?.type === 'button' ? 'Button' : 'Text'}
                  </span>

                  {/* Payload 标签显示 */}
                  {record?.type === 'button' && (record?.payloads?.length ? (
                    <div className="flex flex-wrap gap-1">
                      {record.payloads.slice(0, 3).map((p: any, idx: number) => (
                        <span
                          key={idx}
                          className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-orange-50 text-orange-700 border border-orange-200"
                        >
                          {p.title || p.payload.replace('/', '')}
                        </span>
                      ))}
                      {record.payloads.length > 3 && (
                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                          +{record.payloads.length - 3}
                        </span>
                      )}
                    </div>
                  ) : record?.payload ? (
                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-orange-50 text-orange-700 border border-orange-200">
                      {PAYLOAD_OPTIONS.find(opt => opt.value === record.payload)?.label || record.payload.replace('/', '')}
                    </span>
                  ) : null)}
                </div>
              </div>
            );
          } else {
            // Intent 类型：原有显示逻辑
            return text || <span className="text-gray-400">{t(`common.edit`)}</span>;
          }
        }
      },
      {
        title: t(`common.action`),
        key: 'action',
        width: 120,
        fixed: 'right' as const,
        editable: false,
        render: (_: any, record: any) => {
          const editable = isEditing(record);
          return editable ? (
            <div className="flex space-x-1">
              <Button
                size="small"
                type="link"
                onClick={() => record?.key && save(record.key)}
              >
                {t(`common.save`)}
              </Button>
              <Button
                size="small"
                type="link"
                onClick={cancel}
              >
                {t(`common.cancel`)}
              </Button>
            </div>
          ) : (
            <div className="flex w-full h-full space-x-1">
              <Button
                size="small"
                type="link"
                disabled={editingKey !== ''}
                onClick={() => record?.key && edit(record)}
              >
                {t(`common.edit`)}
              </Button>
              <Popconfirm
                title={t(`common.delete`)}
                onConfirm={() => record?.key && deleteExample(record.key)}
                okText={t(`common.confirm`)}
                cancelText={t(`common.cancel`)}
              >
                <Button
                  size="small"
                  type="link"
                  danger
                  disabled={editingKey !== ''}
                >
                  {t(`common.delete`)}
                </Button>
              </Popconfirm>
            </div>
          );
        },
      },
    ];

    const _columns = columns.map((col) => {
      return {
        ...col,
        onCell: (record: any) => ({
          record,
          dataIndex: col.dataIndex,
          title: col.title,
          editing: col.editable ? isEditing(record) : false,
        }),
      };
    });
    return _columns;
  };

  const addExample = () => {
    const newKey = `example_${Date.now()}`;
    const newExample = menu === 'response'
      ? {
        key: newKey,
        id: exampleData.length,
        type: 'text',
        value: '',
        text: '',
        payloads: undefined
      }
      : {
        key: newKey,
        id: exampleData.length,
        text: ''
      };
    setExampleData([...exampleData, newExample]);
    edit(newExample);
  };

  // 解析实体文字函数
  const parseEntityText = useCallback((text: string) => {
    if (!text) return [];

    const entityRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = entityRegex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push({
          type: 'text',
          content: text.slice(lastIndex, match.index)
        });
      }

      parts.push({
        type: 'entity',
        content: match[1],
        entityName: match[2]
      });

      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
      parts.push({
        type: 'text',
        content: text.slice(lastIndex)
      });
    }

    return parts;
  }, []);

  // 渲染带实体高亮的文本
  const renderHighlightedText = useCallback((text: string) => {
    const parts = parseEntityText(text);

    return parts.map((part, index) => (
      part.type === 'entity' ? (
        <span
          key={index}
          className="text-[var(--color-text-active)] font-medium"
          title={`实体: ${part.entityName}`}
        >
          {part.content}
        </span>
      ) : (
        <span key={index}>{part.content}</span>
      )
    ));
  }, [parseEntityText]);

  const currentStory = useMemo(() => {
    if (!selectKey.length && menu !== 'story') return [];

    const [key] = selectKey;
    const id = treeData.find((item: any) => item.key === key)?.id;
    const selectedData = data?.find((item: any) => item?.id === id);
    return selectedData;
  }, [selectKey, treeData, data, menu]);

  // 搜索结果渲染
  const highlightText = useCallback((text: string, searchValue: string) => {
    if (!searchValue.trim() || !text) return text;

    const regex = new RegExp(`(${searchValue.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const parts = text.split(regex);

    return parts.map((part, index) =>
      regex.test(part) ? (
        <span key={index}>
          {part}
        </span>
      ) : part
    );
  }, []);

  const renderTitle = useCallback((data: any) => {
    const displayName = data?.name || '--';
    const highlightedName = highlightText(displayName, searchValue);

    return (
      <div className='w-full flex justify-between'>
        <span className='truncate w-[140px]' title={displayName}>{highlightedName}</span>
        <span>
          <Dropdown
            overlay={
              <Menu
                onClick={(e) => e.domEvent.preventDefault()}
              >
                <Menu.Item
                  key="edit"
                  className='!p-0'
                  onClick={(e) => {
                    e.domEvent.stopPropagation();
                    handleEdit(data);
                  }}>
                  <PermissionWrapper requiredPermissions={['File Edit']} className='!block'>
                    <Button type='text' className='w-full'>{t(`common.edit`)}</Button>
                  </PermissionWrapper>
                </Menu.Item>
                <Menu.Item
                  key="delete"
                  className='!p-0'
                  onClick={() => {
                    handleDel(data?.id)
                  }}>
                  <PermissionWrapper requiredPermissions={['File Delete']} className='!block'>
                    <Button type='text' className='w-full'>{t(`common.delete`)}</Button>
                  </PermissionWrapper>
                </Menu.Item>
              </Menu>
            }
            trigger={['click']}
          >
            <MoreOutlined
              className="cursor-pointer"
              onClick={(e) => {
                e.stopPropagation();
                e.preventDefault();
              }}
            />
          </Dropdown>
        </span>
      </div>
    )
  }, [handleEdit, handleDel, t, highlightText, searchValue]);

  const onChange = useCallback((value: string) => {
    setSearchValue(value);
    // 如果搜索框清空，清除选中状态
    if (!value.trim()) {
      setSelectKey([]);
    } else {
      // 实时搜索：输入时自动过滤并选择第一个结果
      const filteredData = filterTreeData(data?.map((item: any, index: number) => ({
        key: `${menu}_${item?.id || index}`,
        name: item?.name,
        title: item,
        ...item
      })) || [], value);

      if (filteredData.length > 0) {
        setSelectKey([filteredData[0].key]);
      }
    }
  }, [data, menu, filterTreeData]);

  const onSearch = useCallback((value: string) => {
    // 支持搜索按钮点击，与onChange保持一致的逻辑
    if (value.trim() && treeData.length > 0) {
      setSelectKey([treeData[0].key]);
    }
  }, [treeData]);

  const onSelect = useCallback((key: Key[]) => {
    if (key.length) setSelectKey(key);
  }, []);

  return (
    <>
      <div className={`${contentStyle.flowContainer}`}>
        <Spin spinning={loading}>
          <div className="flex h-full">
            <div className={`mr-1 flex flex-col border-r border-[#f3f4f6] relative z-10 transition-all duration-300 ease-in-out ${showTree ? 'w-[215px] px-2' : 'w-0 p-0'}`}>
              <div className={`flex mb-1 flex-shrink-0 ${!showTree && 'hidden'}`}>
                <Input.Search
                  size="small"
                  className="flex-1"
                  placeholder={`${t('common.search')}...`}
                  allowClear
                  enterButton
                  onSearch={onSearch}
                  onChange={(e) => onChange(e.target.value)}
                  value={searchValue}
                />
                <Button type="primary" size="small" className="ml-1" icon={<PlusOutlined />} onClick={handleAdd} />
              </div>
              {searchValue && treeData.length === 0 && (
                <div className="text-gray-400 text-center py-2 text-sm">
                  {t(`mlops-common.noSearchData`)}
                </div>
              )}
              <div className={`flex-1 overflow-y-auto ${!showTree && 'hidden'}`}>
                <Tree
                  className="w-full h-full"
                  showLine
                  blockNode
                  expandAction={false}
                  defaultExpandAll
                  autoExpandParent
                  treeData={treeData}
                  titleRender={(nodeData: any) => renderTitle(nodeData)}
                  onSelect={onSelect}
                  selectedKeys={selectKey}
                />
              </div>
              <div className='absolute right-0 top-[50%] translate-x-[50%] translate-y-[-60%] z-20'>
                <Button
                  className='border border-gray-200 shadow-md hover:shadow-lg transition-shadow duration-200'
                  size='small'
                  icon={showTree ? <LeftOutlined /> : <RightOutlined />}
                  shape='circle'
                  onClick={() => setShowTree(x => !x)}
                />
              </div>
            </div>
            <div className="flex-1 h-full relative">
              {
                menu === 'story' ? (
                  <StoryFlow
                    dataset={dataset}
                    currentStory={currentStory}
                    onSuccess={onSuccess}
                  />
                ) : supportedItems.includes(menu as any) ? (
                  <div className="h-full flex flex-col border border-gray-200 rounded relative ">

                    {/* 顶部介绍 */}
                    <div className="px-3 py-1 border-b border-gray-200 bg-gray-50">
                      <h1>Examples</h1>
                      <div className="text-xs text-gray-500">
                        {/* {t(`datasets.selectEntityTip`)} */}
                        支持为此{t(`datasets.${menu}`)}批量添加样例，通过换行进行区分。
                        {menu === 'intent' && '同时意图可通过框选关键字，为关键字添加实体'}
                      </div>
                    </div>

                    {/* 内容区域 */}
                    <div className="flex-1 p-3 overflow-hidden relative">
                      <Form form={form} component={false}>
                        <div className="absolute w-[97%]">
                          <Table
                            components={{
                              body: {
                                cell: EditableCell,
                              },
                            }}
                            bordered
                            dataSource={exampleData}
                            columns={getColumns()}
                            rowClassName="editable-row"
                            pagination={false}
                            scroll={{ y: 'calc(100vh - 380px)' }}
                            size="small"
                            locale={{
                              emptyText: (
                                <div className="text-gray-400 text-center py-8">
                                  {t(`common.noData`)}
                                </div>
                              )
                            }}
                          />
                        </div>
                      </Form>
                    </div>

                    {/* 底部工具栏 */}
                    <div className="flex justify-between items-center p-3 border-t border-gray-200 bg-gray-50">
                      <Button
                        type="dashed"
                        icon={<PlusOutlined />}
                        onClick={addExample}
                        size="small"
                      >
                        {t(`common.add`)}
                      </Button>
                      <Button
                        type="primary"
                        size="small"
                        onClick={handleSaveExamples}
                      >
                        {t('common.save')}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-400">
                    不支持的数据类型
                  </div>
                )
              }
            </div>
          </div>
        </Spin>
      </div>

      {/* 实体选择模态框 */}
      <EntitySelectModal
        ref={entityModalRef}
        dataset={dataset}
        onSuccess={handleEntitySelect}
      />
    </>
  );
};

export default ExampleContent;