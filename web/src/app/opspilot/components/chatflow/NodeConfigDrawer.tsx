'use client';

import React, { useState } from 'react';
import { Drawer, Form, Input, Select, InputNumber, Button, message, TimePicker, Upload, Radio } from 'antd';
import { DeleteOutlined, InboxOutlined, CopyOutlined } from '@ant-design/icons';
import { Node } from '@xyflow/react';
import type { UploadProps, UploadFile as AntdUploadFile } from 'antd';
import { useTranslation } from '@/utils/i18n';

// Extend UploadFile to include the 'content' property
interface UploadFile extends AntdUploadFile {
  content?: string;
}
import { useSkillApi } from '@/app/opspilot/api/skill';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import dayjs from 'dayjs';

const { Option } = Select;
const { TextArea } = Input;

// Node data type definition
interface ChatflowNodeData {
  label: string;
  type: string;
  config?: any;
}

// Extended Node type with specific data type
interface ChatflowNode extends Omit<Node, 'data'> {
  data: ChatflowNodeData;
}

interface NodeConfigDrawerProps {
  visible: boolean;
  node: ChatflowNode | null;
  nodes?: ChatflowNode[];
  onClose: () => void;
  onSave: (nodeId: string, config: any) => void;
  onDelete: (nodeId: string) => void;
}

const NodeConfigDrawer: React.FC<NodeConfigDrawerProps> = ({
  visible,
  node,
  nodes = [],
  onClose,
  onSave,
  onDelete
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [frequency, setFrequency] = useState('daily');
  const [paramRows, setParamRows] = useState<Array<{ key: string, value: string }>>([]);
  const [headerRows, setHeaderRows] = useState<Array<{ key: string, value: string }>>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadFile[]>([]);
  const [skills, setSkills] = useState<any[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);

  const { fetchSkill } = useSkillApi();
  const searchParams = useSearchParams();
  const botId = searchParams ? searchParams.get('id') : '1';

  // Load LLM model list
  const loadLlmModels = async () => {
    try {
      setLoadingSkills(true);
      const skills = await fetchSkill({is_template: 0});
      setSkills(skills || []);
    } catch (error) {
      console.error(t('skill.settings.noSkillHasBeenSelected'), error);
      message.error(t('skill.settings.noSkillHasBeenSelected'));
    } finally {
      setLoadingSkills(false);
    }
  };

  // 复制API URL到剪贴板
  const copyApiUrl = async () => {
    const currentOrigin = typeof window !== 'undefined' ? window.location.origin : '';
    const apiUrl = `${currentOrigin}/api/v1/opspilot/bot_mgmt/execute_chat_flow/${botId || '1'}/${node?.id || 'abcdef'}`;
    
    try {
      await navigator.clipboard.writeText(apiUrl);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = apiUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      message.success(t('chatflow.nodeConfig.apiLinkCopied'));
    }
  };

  React.useEffect(() => {
    if (node && visible) {
      const config = node.data.config || {};
      
      // Force form reset to ensure latest node data
      form.resetFields();
      
      // Handle time field conversion to correct dayjs object
      const formValues: any = {
        name: node.data.label,
        ...config
      };

      // Time format handling for celery nodes
      if (node.data.type === 'celery' && config.time) {
        try {
          // String format (e.g., "14:30") to dayjs object
          if (typeof config.time === 'string') {
            const timeStr = config.time.includes(':') ? config.time : `${config.time}:00`;
            const today = new Date().toISOString().split('T')[0];
            formValues.time = dayjs(`${today} ${timeStr}`, 'YYYY-MM-DD HH:mm');
          } else if (config.time && typeof config.time === 'object' && config.time._isAMomentObject) {
            // Convert moment to dayjs
            formValues.time = dayjs(config.time.format('HH:mm'), 'HH:mm');
          } else if (config.time && typeof config.time === 'object' && config.time.$d) {
            // Already dayjs object
            formValues.time = config.time;
          } else {
            formValues.time = dayjs(config.time);
          }
        } catch (error) {
          console.warn('时间格式转换失败:', config.time, error);
          formValues.time = undefined;
        }
      }
      setTimeout(() => {
        form.setFieldsValue(formValues);
      }, 0);

      if (config.frequency) {
        setFrequency(config.frequency);
      } else {
        setFrequency('daily');
      }
      
      // Initialize params and headers based on node type
      const needsParamsAndHeaders = ['http', 'restful', 'openai'];
      
      if (needsParamsAndHeaders.includes(node.data.type)) {
        if ((config as any).params && Array.isArray((config as any).params) && (config as any).params.length > 0) {
          setParamRows([...(config as any).params]);
        } else {
          setParamRows([{ key: '', value: '' }]);
        }
        
        if ((config as any).headers && Array.isArray((config as any).headers) && (config as any).headers.length > 0) {
          setHeaderRows([...(config as any).headers]);
        } else {
          setHeaderRows([{ key: '', value: '' }]);
        }
      } else {
        if ((config as any).params && Array.isArray((config as any).params)) {
          setParamRows([...(config as any).params]);
        } else {
          setParamRows([]);
        }
        
        if ((config as any).headers && Array.isArray((config as any).headers)) {
          setHeaderRows([...(config as any).headers]);
        } else {
          setHeaderRows([]);
        }
      }

      // Initialize uploaded files for agents nodes
      if (node.data.type === 'agents') {
        if (config.uploadedFiles && Array.isArray(config.uploadedFiles)) {
          // Convert saved file data back to upload file format
          const convertedFiles = config.uploadedFiles.map((file: any, index: number) => ({
            uid: file.uid || `file-${index}`,
            name: file.name,
            status: 'done' as const,
            content: file.content,
            response: {
              fileId: file.uid || `file-${index}`,
              fileName: file.name,
              content: file.content
            }
          }));
          setUploadedFiles(convertedFiles);
        } else {
          setUploadedFiles([]);
        }
        loadLlmModels();
      } else {
        setUploadedFiles([]);
      }
    } else {
      // Reset all states when drawer closes
      form.resetFields();
      setParamRows([]);
      setHeaderRows([]);
      setFrequency('daily');
      setUploadedFiles([]);
    }
  }, [node, visible, form]);

  // Save configuration
  const handleSave = () => {
    if (!node) return;

    form.validateFields().then((values) => {
      const configData = {
        ...values,
        params: paramRows.filter(row => row.key && row.value),
        headers: headerRows.filter(row => row.key && row.value)
      };

      // Save uploaded files for agents nodes
      if (node.data.type === 'agents') {
        // Only save name and content from uploaded files
        configData.uploadedFiles = uploadedFiles.map(file => ({
          name: file.name,
          content: file.response?.content || file.content || ''
        }));
      }

      // Save time in HH:mm format for celery nodes
      if (node.data.type === 'celery' && configData.time) {
        try {
          if (configData.time && typeof configData.time === 'object' && configData.time.format) {
            configData.time = configData.time.format('HH:mm');
          }
        } catch (error) {
          console.warn('时间格式保存失败:', configData.time, error);
        }
      }

      onSave(node.id, configData);
      message.success(t('chatflow.messages.nodeConfigured'));
    });
  };

  const handleDelete = () => {
    if (!node) return;
    onDelete(node.id);
    onClose();
  };

  const handleFrequencyChange = (value: string) => {
    setFrequency(value);
    form.setFieldsValue({
      time: undefined,
      weekday: undefined,
      day: undefined
    });
  };

  const addParamRow = () => {
    setParamRows([...paramRows, { key: '', value: '' }]);
  };

  const removeParamRow = (index: number) => {
    if (paramRows.length > 1) {
      setParamRows(paramRows.filter((_, i) => i !== index));
    }
  };

  const updateParamRow = (index: number, field: 'key' | 'value', value: string) => {
    const newRows = [...paramRows];
    newRows[index][field] = value;
    setParamRows(newRows);
  };

  const addHeaderRow = () => {
    setHeaderRows([...headerRows, { key: '', value: '' }]);
  };

  const removeHeaderRow = (index: number) => {
    if (headerRows.length > 1) {
      setHeaderRows(headerRows.filter((_, i) => i !== index));
    }
  };

  const updateHeaderRow = (index: number, field: 'key' | 'value', value: string) => {
    const newRows = [...headerRows];
    newRows[index][field] = value;
    setHeaderRows(newRows);
  };

  // File upload configuration
  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: '.md',
    fileList: uploadedFiles,
    beforeUpload: (file) => {
      if (!file.name.toLowerCase().endsWith('.md')) {
        message.error(t('chatflow.nodeConfig.onlyMdFilesSupported'));
        return false;
      }
      
      const isLt10M = file.size / 1024 / 1024 < 10;
      if (!isLt10M) {
        message.error(t('chatflow.nodeConfig.fileSizeLimit'));
        return false;
      }
      
      return true;
    },
    onChange: (info) => {
      setUploadedFiles([...info.fileList]);
    },
    onRemove: (file) => {
      const newFileList = uploadedFiles.filter(item => item.uid !== file.uid);
      setUploadedFiles(newFileList);
      message.success(t('chatflow.nodeConfig.fileDeleted'));
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        // Read file content
        const fileContent = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target?.result as string);
          reader.onerror = reject;
          reader.readAsText(file as File);
        });

        // Generate UID for the file
        const fileUid = `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

        // Create file object with content
        const fileWithContent = {
          uid: fileUid,
          name: (file as File).name,
          content: fileContent,
          status: 'done' as const,
          response: {
            fileId: fileUid,
            fileName: (file as File).name,
            content: fileContent
          }
        };

        onSuccess && onSuccess(fileWithContent.response);
      } catch (error) {
        console.error('File read error:', error);
        onError && onError(new Error(t('chatflow.nodeConfig.fileReadError')));
      }
    }
  };

  // Get trigger nodes list for condition branch configuration
  const getTriggerNodes = () => {
    const triggerTypes = ['celery', 'restful', 'openai'];
    
    // Safety checks
    if (!nodes) {
      console.warn('NodeConfigDrawer: nodes is null or undefined');
      return [];
    }
    
    if (!Array.isArray(nodes)) {
      console.warn('NodeConfigDrawer: nodes is not an array:', typeof nodes, nodes);
      return [];
    }
    
    try {
      return nodes.filter(n => {
        // Ensure node has correct data structure
        if (!n || !n.data || typeof n.data.type !== 'string') {
          console.warn('NodeConfigDrawer: Invalid node structure:', n);
          return false;
        }
        return triggerTypes.includes(n.data.type);
      });
    } catch (error) {
      console.error('NodeConfigDrawer: Error filtering trigger nodes:', error);
      return [];
    }
  };

  const renderConfigForm = () => {
    if (!node) return null;

    const nodeType = node.data.type;

    return (
      <>
        {/* Common node name configuration for all node types */}
        <Form.Item name="name" label={t('chatflow.nodeConfig.nodeName')} rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseEnterNodeName') }]}>
          <Input placeholder={t('chatflow.nodeConfig.pleaseEnterNodeName')} />
        </Form.Item>

        {/* Common input and output parameters for all node types */}
        <Form.Item name="inputParams" label={t('chatflow.nodeConfig.inputParams')} rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseEnterInputParams') }]}>
          <Input placeholder={t('chatflow.nodeConfig.pleaseEnterInputParams')} />
        </Form.Item>
        
        <Form.Item name="outputParams" label={t('chatflow.nodeConfig.outputParams')} rules={[{ required: true, message: t('chatflow.nodeConfig.pleaseEnterOutputParams') }]}>
          <Input placeholder={t('chatflow.nodeConfig.pleaseEnterOutputParams')} />
        </Form.Item>

        {/* Render specific configuration based on node type */}
        {(() => {
          switch (nodeType) {
            case 'celery':
              return (
                <>
                  <Form.Item name="frequency" label={t('chatflow.nodeConfig.triggerFrequency')} rules={[{ required: true }]}>
                    <Select placeholder={t('chatflow.nodeConfig.pleaseSelectTriggerFrequency')} onChange={handleFrequencyChange}>
                      <Option value="daily">{t('chatflow.daily')}</Option>
                      <Option value="weekly">{t('chatflow.weekly')}</Option>
                      <Option value="monthly">{t('chatflow.monthly')}</Option>
                    </Select>
                  </Form.Item>

                  {frequency === 'daily' && (
                    <Form.Item name="time" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
                      <TimePicker
                        format="HH:mm"
                        placeholder={t('chatflow.nodeConfig.selectTime')}
                        className="w-full"
                      />
                    </Form.Item>
                  )}

                  {frequency === 'weekly' && (
                    <>
                      <Form.Item name="weekday" label={t('chatflow.weekday')} rules={[{ required: true }]}>
                        <Select placeholder={t('chatflow.nodeConfig.selectWeekday')}>
                          <Option value={1}>{t('chatflow.nodeConfig.monday')}</Option>
                          <Option value={2}>{t('chatflow.nodeConfig.tuesday')}</Option>
                          <Option value={3}>{t('chatflow.nodeConfig.wednesday')}</Option>
                          <Option value={4}>{t('chatflow.nodeConfig.thursday')}</Option>
                          <Option value={5}>{t('chatflow.nodeConfig.friday')}</Option>
                          <Option value={6}>{t('chatflow.nodeConfig.saturday')}</Option>
                          <Option value={0}>{t('chatflow.nodeConfig.sunday')}</Option>
                        </Select>
                      </Form.Item>
                      <Form.Item name="time" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
                        <TimePicker
                          format="HH:mm"
                          placeholder={t('chatflow.nodeConfig.selectTime')}
                          className="w-full"
                        />
                      </Form.Item>
                    </>
                  )}

                  {frequency === 'monthly' && (
                    <>
                      <Form.Item name="day" label={t('chatflow.day')} rules={[{ required: true }]}>
                        <Select placeholder={t('chatflow.nodeConfig.selectDay')}>
                          {Array.from({ length: 31 }, (_, i) => (
                            <Option key={i + 1} value={i + 1}>{i + 1}</Option>
                          ))}
                        </Select>
                      </Form.Item>
                      <Form.Item name="time" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
                        <TimePicker
                          format="HH:mm"
                          placeholder={t('chatflow.nodeConfig.selectTime')}
                          className="w-full"
                        />
                      </Form.Item>
                    </>
                  )}

                  <Form.Item name="message" label={t('chatflow.nodeConfig.triggerMessage')}>
                    <TextArea rows={3} placeholder={t('chatflow.nodeConfig.triggerMessagePlaceholder')} />
                  </Form.Item>
                </>
              );

            case 'http':
              return (
                <>
                  <Form.Item label="API" required>
                    <div className="flex gap-2">
                      <Form.Item name="method" noStyle rules={[{ required: true }]}>
                        <Select style={{ width: 100 }} placeholder={t('chatflow.nodeConfig.apiMethod')}>
                          <Option value="GET">GET</Option>
                          <Option value="POST">POST</Option>
                          <Option value="PUT">PUT</Option>
                          <Option value="DELETE">DELETE</Option>
                        </Select>
                      </Form.Item>
                      <Form.Item name="url" noStyle rules={[{ required: true }]}>
                        <Input placeholder={t('chatflow.nodeConfig.enterUrl')} className="flex-1" />
                      </Form.Item>
                    </div>
                  </Form.Item>

                  <Form.Item label={t('chatflow.nodeConfig.requestParams')}>
                    <div className="space-y-2">
                      <div className="grid gap-2 text-sm text-gray-500 mb-1 grid-cols-[1fr_1fr_60px]">
                        <span>{t('chatflow.nodeConfig.paramName')}</span>
                        <span>{t('chatflow.nodeConfig.paramValue')}</span>
                        <span>{t('chatflow.nodeConfig.operation')}</span>
                      </div>
                      {paramRows.map((row, index) => (
                        <div key={index} className="grid gap-2 items-center grid-cols-[1fr_1fr_60px]">
                          <Input
                            placeholder={t('chatflow.nodeConfig.enterParamName')}
                            value={row.key}
                            onChange={(e) => updateParamRow(index, 'key', e.target.value)}
                          />
                          <div className="flex items-center gap-1">
                            <span className="text-xs bg-[var(--color-fill-1)] px-1 rounded">str</span>
                            <Input
                              placeholder={t('chatflow.nodeConfig.enterOrReferenceParamValue')}
                              value={row.value}
                              onChange={(e) => updateParamRow(index, 'value', e.target.value)}
                            />
                          </div>
                          <div className="flex gap-1">
                            <Button
                              type="text"
                              size="small"
                              icon="+"
                              onClick={addParamRow}
                            />
                            <Button
                              type="text"
                              size="small"
                              icon="-"
                              onClick={() => removeParamRow(index)}
                              disabled={paramRows.length === 1}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Form.Item>

                  <Form.Item label={t('chatflow.nodeConfig.requestHeaders')}>
                    <div className="space-y-2">
                      <div className="grid gap-2 text-sm text-gray-500 mb-1 grid-cols-[1fr_1fr_60px]">
                        <span>{t('chatflow.nodeConfig.paramName')}</span>
                        <span>{t('chatflow.nodeConfig.paramValue')}</span>
                        <span>{t('chatflow.nodeConfig.operation')}</span>
                      </div>
                      {headerRows.map((row, index) => (
                        <div key={index} className="grid gap-2 items-center grid-cols-[1fr_1fr_60px]">
                          <Input
                            placeholder={t('chatflow.nodeConfig.enterParamName')}
                            value={row.key}
                            onChange={(e) => updateHeaderRow(index, 'key', e.target.value)}
                          />
                          <div className="flex items-center gap-1">
                            <span className="text-xs bg-[var(--color-fill-1)] px-1 rounded">str</span>
                            <Input
                              placeholder={t('chatflow.nodeConfig.enterOrReferenceParamValue')}
                              value={row.value}
                              onChange={(e) => updateHeaderRow(index, 'value', e.target.value)}
                            />
                          </div>
                          <div className="flex gap-1">
                            <Button
                              type="text"
                              size="small"
                              icon="+"
                              onClick={addHeaderRow}
                            />
                            <Button
                              type="text"
                              size="small"
                              icon="-"
                              onClick={() => removeHeaderRow(index)}
                              disabled={headerRows.length === 1}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </Form.Item>

                  <Form.Item name="requestBody" label={t('chatflow.nodeConfig.requestBody')}>
                    <TextArea rows={6} placeholder={t('chatflow.nodeConfig.requestBodyPlaceholder')} />
                  </Form.Item>

                  <Form.Item name="timeout" label={t('chatflow.nodeConfig.timeoutSettings')}>
                    <InputNumber min={1} max={300} className="w-full" />
                  </Form.Item>

                  <Form.Item name="outputMode" label={t('chatflow.nodeConfig.outputMode')}>
                    <Radio.Group>
                      <Radio value="stream">{t('chatflow.nodeConfig.streamMode')}</Radio>
                      <Radio value="once">{t('chatflow.nodeConfig.onceMode')}</Radio>
                    </Radio.Group>
                  </Form.Item>
                </>
              );

            case 'agents':
              // Handle agent selection, save both name and ID
              const handleAgentChange = (agentId: string) => {
                const selectedAgent = skills.find(model => model.id === agentId);
                if (selectedAgent) {
                  form.setFieldsValue({
                    agent: agentId,
                    agentName: selectedAgent.name
                  });
                }
              };

              return (
                <>
                  <Form.Item name="agent" label={t('chatflow.nodeConfig.selectAgent')} rules={[{ required: true }]}>
                    <Select 
                      placeholder={t('chatflow.nodeConfig.pleaseSelectAgent')}
                      loading={loadingSkills}
                      disabled={loadingSkills}
                      showSearch
                      onChange={handleAgentChange}
                      filterOption={(input, option) =>
                        option?.label?.toString().toLowerCase().includes(input.toLowerCase()) ?? false
                      }
                    >
                      {skills.map((model) => (
                        <Option key={model.id} value={model.id} label={model.name}>
                          {model.name}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                  {/* Hidden field to save agent name */}
                  <Form.Item name="agentName" className="hidden">
                    <Input />
                  </Form.Item>

                  {/* Prompt 追加功能 */}
                  <Form.Item 
                    name="prompt" 
                    label={t('chatflow.nodeConfig.promptAppend')}
                    tooltip={t('chatflow.nodeConfig.promptAppendTooltip')}>
                    <TextArea rows={4} placeholder={t('chatflow.nodeConfig.promptPlaceholder')} />
                  </Form.Item>

                  {/* 知识追加功能 */}
                  <Form.Item 
                    label={t('chatflow.nodeConfig.uploadKnowledge')}
                    tooltip={t('chatflow.nodeConfig.uploadKnowledgeTooltip')}>
                    <Upload.Dragger {...uploadProps}>
                      <p className="ant-upload-drag-icon">
                        <InboxOutlined />
                      </p>
                      <p className="ant-upload-text">{t('chatflow.nodeConfig.uploadHint')}</p>
                      <p className="ant-upload-hint">{t('chatflow.nodeConfig.uploadDescription')}</p>
                    </Upload.Dragger>
                  </Form.Item>
                </>
              );

            case 'restful':
              const currentOrigin = typeof window !== 'undefined' ? window.location.origin : '';
              const restfulApiUrl = `${currentOrigin}/api/v1/opspilot/bot_mgmt/execute_chat_flow/${botId || '1'}/${node?.id || 'abcdef'}`;
              
              return (
                <>
                  <div className="p-4 bg-blue-50 border border-blue-200 rounded-md text-xs leading-5">
                    <p className="text-gray-500 mb-2">
                      {t('chatflow.nodeConfig.restfulApiInfo')}
                    </p>
                    <div className="mt-2 mb-2 relative">
                      <Input.TextArea
                        readOnly
                        value={restfulApiUrl}
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        className="font-mono text-xs text-gray-700 bg-white pr-10 border-none"
                      />
                      <Button
                        type="text"
                        icon={<CopyOutlined />}
                        size="small"
                        onClick={copyApiUrl}
                        className="absolute top-2 right-2 z-10 text-gray-500 hover:text-[var(--color-primary)]"
                        title={t('chatflow.nodeConfig.copyLink')}
                      />
                    </div>
                    <span className="text-gray-500">{t('chatflow.nodeConfig.moreDetails')}</span>
                    <Link href="/opspilot/studio/detail/api" target="_blank" className="text-blue-500 hover:underline">
                      {t('chatflow.nodeConfig.viewApiDocs')}
                    </Link>
                  </div>
                </>
              );

            case 'openai':
              const currentOriginForOpenai = typeof window !== 'undefined' ? window.location.origin : '';
              const openaiApiUrl = `${currentOriginForOpenai}/api/v1/opspilot/bot_mgmt/execute_chat_flow/${botId || '1'}/${node?.id || 'abcdef'}`;
              
              return (
                <>
                  <div className="p-4 bg-blue-50 border border-blue-200 rounded-md text-xs leading-5">
                    <p className="text-gray-500 mb-2">
                      {t('chatflow.nodeConfig.openaiApiInfo')}
                    </p>
                    <div className="mt-2 mb-2 relative">
                      <Input.TextArea
                        readOnly
                        value={openaiApiUrl}
                        autoSize={{ minRows: 2, maxRows: 4 }}
                        className="font-mono text-xs text-gray-700 bg-white pr-10 border-none"
                      />
                      <Button
                        type="text"
                        icon={<CopyOutlined />}
                        size="small"
                        onClick={copyApiUrl}
                        className="absolute top-2 right-2 z-10 text-gray-500 hover:text-[var(--color-primary)]"
                        title={t('chatflow.nodeConfig.copyLink')}
                      />
                    </div>
                    <span className="text-gray-500">{t('chatflow.nodeConfig.moreDetails')}</span>
                    <Link href="/opspilot/studio/detail/api" target="_blank" className="text-blue-500 hover:underline">
                      {t('chatflow.nodeConfig.viewApiDocs')}
                    </Link>
                  </div>
                </>
              );

            case 'condition':
              const triggerNodes = getTriggerNodes();
              
              return (
                <>
                  <div className="mb-4">
                    <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.branchCondition')}</h4>
                    <div className="grid grid-cols-3 gap-2">
                      <Form.Item name="conditionField" rules={[{ required: true }]}>
                        <Select placeholder={t('chatflow.nodeConfig.conditionField')}>
                          <Option value="triggerType">{t('chatflow.nodeConfig.triggerType')}</Option>
                        </Select>
                      </Form.Item>
                      <Form.Item name="conditionOperator" rules={[{ required: true }]}>
                        <Select placeholder={t('chatflow.nodeConfig.conditionOperator')}>
                          <Option value="equals">{t('chatflow.nodeConfig.equals')}</Option>
                          <Option value="notEquals">{t('chatflow.nodeConfig.notEquals')}</Option>
                        </Select>
                      </Form.Item>
                      <Form.Item name="conditionValue" rules={[{ required: true }]}>
                        <Select placeholder={t('chatflow.nodeConfig.selectValue')}>
                          {triggerNodes.length === 0 ? (
                            <Option value="" disabled>{t('chatflow.nodeConfig.noTriggerNodes')}</Option>
                          ) : (
                            triggerNodes.map((triggerNode) => (
                              <Option key={triggerNode.id} value={triggerNode.id}>
                                {triggerNode.data.label}
                              </Option>
                            ))
                          )}
                        </Select>
                      </Form.Item>
                    </div>
                    <div className="mt-4 p-3 bg-[var(--color-fill-1)] rounded-md">
                      <p className="text-xs text-gray-600 mb-2">{t('chatflow.nodeConfig.connectionDescription')}</p>
                      <div className="flex items-center gap-2 text-xs">
                        <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                        <span>{t('chatflow.nodeConfig.truePathDescription')}</span>
                      </div>
                      <div className="flex items-center gap-2 text-xs mt-1">
                        <div className="w-3 h-3 bg-red-500 rounded-full"></div>
                        <span>{t('chatflow.nodeConfig.falsePathDescription')}</span>
                      </div>
                    </div>
                  </div>
                </>
              );

            default:
              return null;
          }
        })()}
      </>
    );
  };

  return (
    <Drawer
      title={String(node?.data.label || '')}
      open={visible}
      onClose={onClose}
      width={480}
      placement="right"
      footer={
        <div className="flex justify-end gap-2">
          <Button
            danger
            icon={<DeleteOutlined />}
            onClick={handleDelete}
          >
            {t('chatflow.nodeConfig.deleteNode')}
          </Button>
          <Button onClick={onClose}>
            {t('chatflow.nodeConfig.cancel')}
          </Button>
          <Button type="primary" onClick={handleSave}>
            {t('chatflow.nodeConfig.confirm')}
          </Button>
        </div>
      }
    >
      <Form form={form} layout="vertical">
        {renderConfigForm()}
      </Form>
    </Drawer>
  );
};

export default NodeConfigDrawer;