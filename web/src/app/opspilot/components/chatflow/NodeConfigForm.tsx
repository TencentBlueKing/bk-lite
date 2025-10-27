'use client';

import React from 'react';
import { Form, Input, Select, InputNumber, Button, TimePicker, Upload, Radio } from 'antd';
import { InboxOutlined, CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import Link from 'next/link';
import { message } from 'antd';
import type { UploadProps } from 'antd';

const { Option } = Select;
const { TextArea } = Input;

export const NodeConfigForm: React.FC<any> = ({
  node,
  nodes,
  botId,
  frequency,
  onFrequencyChange,
  paramRows,
  headerRows,
  uploadedFiles,
  setUploadedFiles,
  skills,
  loadingSkills,
  notificationChannels,
  loadingChannels,
  notificationType,
  setNotificationType,
  loadChannels,
  allUsers,
  loadingUsers,
  form,
}) => {
  const { t } = useTranslation();
  const nodeType = node.data.type;

  // 复制 API URL
  const copyApiUrl = async () => {
    const currentOrigin = typeof window !== 'undefined' ? window.location.origin : '';
    const apiUrl = `${currentOrigin}/api/v1/opspilot/bot_mgmt/execute_chat_flow/${botId}/${node.id}`;
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

  // 文件上传配置
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
      if (file.size / 1024 / 1024 >= 10) {
        message.error(t('chatflow.nodeConfig.fileSizeLimit'));
        return false;
      }
      return true;
    },
    onChange: (info) => setUploadedFiles([...info.fileList]),
    onRemove: (file) => {
      setUploadedFiles(uploadedFiles.filter((item: any) => item.uid !== file.uid));
      message.success(t('chatflow.nodeConfig.fileDeleted'));
    },
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        const fileContent = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => resolve(e.target?.result as string);
          reader.onerror = reject;
          reader.readAsText(file as File);
        });
        const fileUid = `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const fileWithContent = {
          uid: fileUid,
          name: (file as File).name,
          content: fileContent,
          status: 'done' as const,
          response: { fileId: fileUid, fileName: (file as File).name, content: fileContent }
        };
        onSuccess && onSuccess(fileWithContent.response);
      } catch (error) {
        console.error('File read error:', error);
        onError && onError(new Error(t('chatflow.nodeConfig.fileReadError')));
      }
    }
  };

  // 渲染键值对编辑器
  const renderKeyValueEditor = (rows: any, label: string) => {
    const { rows: items, addRow, removeRow, updateRow } = rows;
    return (
      <Form.Item label={label}>
        <div className="space-y-2">
          <div className="grid gap-2 text-sm text-gray-500 mb-1 grid-cols-[1fr_1fr_60px]">
            <span>{t('chatflow.nodeConfig.paramName')}</span>
            <span>{t('chatflow.nodeConfig.paramValue')}</span>
            <span>{t('chatflow.nodeConfig.operation')}</span>
          </div>
          {items.map((row: any, index: number) => (
            <div key={index} className="grid gap-2 items-center grid-cols-[1fr_1fr_60px]">
              <Input
                placeholder={t('chatflow.nodeConfig.enterParamName')}
                value={row.key}
                onChange={(e) => updateRow(index, 'key', e.target.value)}
              />
              <div className="flex items-center gap-1">
                <span className="text-xs bg-[var(--color-fill-1)] px-1 rounded">str</span>
                <Input
                  placeholder={t('chatflow.nodeConfig.enterOrReferenceParamValue')}
                  value={row.value}
                  onChange={(e) => updateRow(index, 'value', e.target.value)}
                />
              </div>
              <div className="flex gap-1">
                <Button type="text" size="small" icon="+" onClick={addRow} />
                <Button type="text" size="small" icon="-" onClick={() => removeRow(index)} disabled={items.length === 1} />
              </div>
            </div>
          ))}
        </div>
      </Form.Item>
    );
  };

  return (
    <>
      {/* 通用字段 */}
      <Form.Item name="name" label={t('chatflow.nodeConfig.nodeName')} rules={[{ required: true }]}>
        <Input placeholder={t('chatflow.nodeConfig.pleaseEnterNodeName')} />
      </Form.Item>
      <Form.Item name="inputParams" label={t('chatflow.nodeConfig.inputParams')} rules={[{ required: true }]}>
        <Input placeholder={t('chatflow.nodeConfig.pleaseEnterInputParams')} />
      </Form.Item>
      <Form.Item name="outputParams" label={t('chatflow.nodeConfig.outputParams')} rules={[{ required: true }]}>
        <Input placeholder={t('chatflow.nodeConfig.pleaseEnterOutputParams')} />
      </Form.Item>

      {/* 根据节点类型渲染特定配置 */}
      {nodeType === 'celery' && (
        <>
          <Form.Item name="frequency" label={t('chatflow.nodeConfig.triggerFrequency')} rules={[{ required: true }]}>
            <Select placeholder={t('chatflow.nodeConfig.pleaseSelectTriggerFrequency')} onChange={onFrequencyChange}>
              <Option value="daily">{t('chatflow.daily')}</Option>
              <Option value="weekly">{t('chatflow.weekly')}</Option>
              <Option value="monthly">{t('chatflow.monthly')}</Option>
            </Select>
          </Form.Item>
          {frequency === 'daily' && (
            <Form.Item name="time" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
              <TimePicker format="HH:mm" placeholder={t('chatflow.nodeConfig.selectTime')} className="w-full" />
            </Form.Item>
          )}
          {frequency === 'weekly' && (
            <>
              <Form.Item name="weekday" label={t('chatflow.weekday')} rules={[{ required: true }]}>
                <Select placeholder={t('chatflow.nodeConfig.selectWeekday')}>
                  {[1, 2, 3, 4, 5, 6, 0].map(day => (
                    <Option key={day} value={day}>{t(`chatflow.nodeConfig.${['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'][day]}`)}</Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item name="time" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
                <TimePicker format="HH:mm" placeholder={t('chatflow.nodeConfig.selectTime')} className="w-full" />
              </Form.Item>
            </>
          )}
          {frequency === 'monthly' && (
            <>
              <Form.Item name="day" label={t('chatflow.day')} rules={[{ required: true }]}>
                <Select placeholder={t('chatflow.nodeConfig.selectDay')}>
                  {Array.from({ length: 31 }, (_, i) => <Option key={i + 1} value={i + 1}>{i + 1}</Option>)}
                </Select>
              </Form.Item>
              <Form.Item name="time" label={t('chatflow.nodeConfig.triggerTime')} rules={[{ required: true }]}>
                <TimePicker format="HH:mm" placeholder={t('chatflow.nodeConfig.selectTime')} className="w-full" />
              </Form.Item>
            </>
          )}
          <Form.Item name="message" label={t('chatflow.nodeConfig.triggerMessage')}>
            <TextArea rows={3} placeholder={t('chatflow.nodeConfig.triggerMessagePlaceholder')} />
          </Form.Item>
        </>
      )}

      {nodeType === 'http' && (
        <>
          <Form.Item label="API" required>
            <div className="flex gap-2">
              <Form.Item name="method" noStyle rules={[{ required: true }]}>
                <Select style={{ width: 100 }}>
                  {['GET', 'POST', 'PUT', 'DELETE'].map(m => <Option key={m} value={m}>{m}</Option>)}
                </Select>
              </Form.Item>
              <Form.Item name="url" noStyle rules={[{ required: true }]}>
                <Input placeholder={t('chatflow.nodeConfig.enterUrl')} className="flex-1" />
              </Form.Item>
            </div>
          </Form.Item>
          {renderKeyValueEditor(paramRows, t('chatflow.nodeConfig.requestParams'))}
          {renderKeyValueEditor(headerRows, t('chatflow.nodeConfig.requestHeaders'))}
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
      )}

      {nodeType === 'agents' && (
        <>
          <Form.Item name="agent" label={t('chatflow.nodeConfig.selectAgent')} rules={[{ required: true }]}>
            <Select
              placeholder={t('chatflow.nodeConfig.pleaseSelectAgent')}
              loading={loadingSkills}
              showSearch
              onChange={(agentId) => {
                const selectedAgent = skills.find((s: any) => s.id === agentId);
                if (selectedAgent) form.setFieldsValue({ agentName: selectedAgent.name });
              }}
              filterOption={(input, option) => option?.label?.toString().toLowerCase().includes(input.toLowerCase()) ?? false}
            >
              {skills.map((s: any) => <Option key={s.id} value={s.id} label={s.name}>{s.name}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="agentName" className="hidden"><Input /></Form.Item>
          <Form.Item name="prompt" label={t('chatflow.nodeConfig.promptAppend')} tooltip={t('chatflow.nodeConfig.promptAppendTooltip')}>
            <TextArea rows={4} placeholder={t('chatflow.nodeConfig.promptPlaceholder')} />
          </Form.Item>
          <Form.Item label={t('chatflow.nodeConfig.uploadKnowledge')} tooltip={t('chatflow.nodeConfig.uploadKnowledgeTooltip')}>
            <Upload.Dragger {...uploadProps}>
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p className="ant-upload-text">{t('chatflow.nodeConfig.uploadHint')}</p>
              <p className="ant-upload-hint">{t('chatflow.nodeConfig.uploadDescription')}</p>
            </Upload.Dragger>
          </Form.Item>
        </>
      )}

      {(nodeType === 'restful' || nodeType === 'openai') && (
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-md text-xs leading-5">
          <p className="text-gray-500 mb-2">{t(`chatflow.nodeConfig.${nodeType}ApiInfo`)}</p>
          <div className="mt-2 mb-2 relative">
            <Input.TextArea
              readOnly
              value={`${typeof window !== 'undefined' ? window.location.origin : ''}/api/v1/opspilot/bot_mgmt/execute_chat_flow/${botId}/${node.id}`}
              autoSize={{ minRows: 2, maxRows: 4 }}
              className="font-mono text-xs text-gray-700 bg-white pr-10 border-none"
            />
            <Button type="text" icon={<CopyOutlined />} size="small" onClick={copyApiUrl} className="absolute top-2 right-2" />
          </div>
          <span className="text-gray-500">{t('chatflow.nodeConfig.moreDetails')}</span>
          <Link href="/opspilot/studio/detail/api" target="_blank" className="text-blue-500 hover:underline">
            {t('chatflow.nodeConfig.viewApiDocs')}
          </Link>
        </div>
      )}

      {nodeType === 'condition' && (
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
                {nodes.filter((n: any) => ['celery', 'restful', 'openai'].includes(n.data?.type)).map((n: any) => (
                  <Option key={n.id} value={n.id}>{n.data.label}</Option>
                ))}
              </Select>
            </Form.Item>
          </div>
        </div>
      )}

      {nodeType === 'notification' && (
        <>
          <Form.Item name="notificationType" label={t('chatflow.notificationCategory')} initialValue="email" rules={[{ required: true }]}>
            <Radio.Group onChange={(e) => { setNotificationType(e.target.value); loadChannels(e.target.value); }}>
              <Radio value="email">{t('chatflow.email')}</Radio>
              <Radio value="enterprise_wechat_bot">{t('chatflow.enterpriseWechatBot')}</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="notificationMethod" label={t('chatflow.notificationMethod')} rules={[{ required: true }]}>
            <Select placeholder={t('chatflow.selectNotificationMethod')} loading={loadingChannels}>
              {notificationChannels.map((c: any) => <Option key={c.id} value={c.id}>{c.name}</Option>)}
            </Select>
          </Form.Item>
          {notificationType === 'email' && (
            <>
              <Form.Item name="notificationRecipients" label={t('chatflow.notificationRecipients')} rules={[{ required: true }]}>
                <Select mode="multiple" placeholder={t('chatflow.selectNotificationRecipients')} loading={loadingUsers} showSearch>
                  {allUsers.map((u: any) => <Option key={u.id} value={u.id} label={`${u.display_name || u.name}(${u.username})`}>{u.display_name || u.name}({u.username})</Option>)}
                </Select>
              </Form.Item>
              <Form.Item name="notificationTitle" label={t('chatflow.notificationTitle')} rules={[{ required: true }]}>
                <Input placeholder={t('chatflow.enterNotificationTitle')} />
              </Form.Item>
            </>
          )}
          <Form.Item name="notificationContent" label={t('chatflow.notificationContent')} rules={[{ required: true }]} initialValue="last_message">
            <TextArea rows={4} placeholder={t('chatflow.enterNotificationContent')} />
          </Form.Item>
        </>
      )}

      {nodeType === 'enterprise_wechat' && (
        <div className="p-4 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded-md">
          <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.enterpriseWechatParams')}</h4>
          <div className="space-y-3">
            {['token', 'secret', 'aes_key', 'corp_id', 'agent_id'].map((field, idx) => (
              <Form.Item 
                key={field} 
                name={field} 
                label={field.toUpperCase().replace('_', ' ')} 
                rules={[{ 
                  required: true, 
                  message: `请输入${field.toUpperCase().replace('_', ' ')}`,
                  whitespace: true
                }]} 
                className={idx === 4 ? 'mb-0' : 'mb-3'}
              >
                {field.includes('secret') || field === 'aes_key' ? 
                  <Input.Password placeholder={`请输入${field.toUpperCase().replace('_', ' ')}`} /> : 
                  <Input placeholder={`请输入${field.toUpperCase().replace('_', ' ')}`} />
                }
              </Form.Item>
            ))}
          </div>
        </div>
      )}

      {nodeType === 'dingtalk' && (
        <div className="p-4 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded-md">
          <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.dingtalkParams')}</h4>
          <div className="space-y-3">
            <Form.Item 
              name="client_id" 
              label="Client ID" 
              rules={[{ 
                required: true, 
                message: t('chatflow.nodeConfig.pleaseEnterClientId'),
                whitespace: true
              }]}
            >
              <Input placeholder={t('chatflow.nodeConfig.enterClientId')} />
            </Form.Item>
            <Form.Item 
              name="client_secret" 
              label="Client Secret" 
              rules={[{ 
                required: true, 
                message: t('chatflow.nodeConfig.pleaseEnterClientSecret'),
                whitespace: true
              }]}
              className="mb-0"
            >
              <Input.Password placeholder={t('chatflow.nodeConfig.enterClientSecret')} />
            </Form.Item>
          </div>
        </div>
      )}

      {nodeType === 'wechat_official' && (
        <div className="p-4 bg-[var(--color-fill-1)] border border-[var(--color-border-2)] rounded-md">
          <h4 className="text-sm font-medium mb-3">{t('chatflow.nodeConfig.wechatOfficialParams')}</h4>
          <div className="space-y-3">
            {['token', 'appid', 'secret', 'aes_key'].map((field, idx) => (
              <Form.Item 
                key={field} 
                name={field} 
                label={field.toUpperCase().replace('_', ' ')} 
                rules={[{ 
                  required: true, 
                  message: `请输入${field.toUpperCase().replace('_', ' ')}`,
                  whitespace: true
                }]} 
                className={idx === 3 ? 'mb-0' : 'mb-3'}
              >
                {field.includes('secret') || field === 'aes_key' ? 
                  <Input.Password placeholder={`请输入${field.toUpperCase().replace('_', ' ')}`} /> : 
                  <Input placeholder={`请输入${field.toUpperCase().replace('_', ' ')}`} />
                }
              </Form.Item>
            ))}
          </div>
        </div>
      )}
    </>
  );
};
