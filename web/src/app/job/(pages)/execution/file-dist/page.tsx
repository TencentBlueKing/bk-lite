'use client';

import React, { useState } from 'react';
import {
  Form,
  Input,
  Radio,
  Button,
  Upload,
  Divider,
  message,
  Modal,
} from 'antd';
import { PlusOutlined, InboxOutlined, FileOutlined, CloseOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useJobApi from '@/app/job/api';
import HostSelectionModal, { HostItem } from '@/app/job/components/host-selection-modal';

const { Dragger } = Upload;

const FileDistPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { uploadDistributionFile, createFileDistribution, getEnabledDangerousPaths } = useJobApi();
  const [form] = Form.useForm();

  const [hostModalOpen, setHostModalOpen] = useState(false);
  const [selectedHostKeys, setSelectedHostKeys] = useState<string[]>([]);
  const [selectedHosts, setSelectedHosts] = useState<HostItem[]>([]);

  // Store raw File objects on frontend, no upload API call
  const [localFiles, setLocalFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const handleHostConfirm = (keys: string[], hosts: HostItem[]) => {
    setSelectedHostKeys(keys);
    setSelectedHosts(hosts);
    setHostModalOpen(false);
  };

  const handleRemoveFile = (index: number) => {
    setLocalFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const formatFileSize = (bytes: number) => {
    if (!bytes) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Check target path against dangerous path rules
  const checkDangerousPaths = async (targetPath: string): Promise<{ canExecute: boolean; needConfirm: boolean; matchedRules: string[]; apiError?: boolean }> => {
    try {
      console.log('[DangerousPath] Calling API...');
      const rules = await getEnabledDangerousPaths();
      console.log('[DangerousPath] API response:', rules);
      
      const matchedForbidden: string[] = [];
      const matchedConfirm: string[] = [];

      // Helper to extract pattern from rule (could be string or object)
      const getPattern = (rule: string | { pattern?: string; match_pattern?: string; name?: string }): string => {
        if (typeof rule === 'string') return rule;
        return rule.pattern || rule.match_pattern || rule.name || '';
      };

      // Check forbidden paths - match if path contains or starts with the pattern
      for (const rule of rules.forbidden || []) {
        const pattern = getPattern(rule);
        if (pattern && (targetPath.includes(pattern) || pattern.includes(targetPath) || targetPath.startsWith(pattern))) {
          matchedForbidden.push(pattern);
        }
      }

      // Check confirm paths
      for (const rule of rules.confirm || []) {
        const pattern = getPattern(rule);
        if (pattern && (targetPath.includes(pattern) || pattern.includes(targetPath) || targetPath.startsWith(pattern))) {
          matchedConfirm.push(pattern);
        }
      }

      console.log('[DangerousPath] Matched forbidden:', matchedForbidden, 'confirm:', matchedConfirm);

      if (matchedForbidden.length > 0) {
        return { canExecute: false, needConfirm: false, matchedRules: matchedForbidden };
      }

      if (matchedConfirm.length > 0) {
        return { canExecute: true, needConfirm: true, matchedRules: matchedConfirm };
      }

      return { canExecute: true, needConfirm: false, matchedRules: [] };
    } catch (error) {
      console.error('[DangerousPath] API error:', error);
      // API failed - still allow execution but backend will validate
      message.warning(t('common.networkError') || '无法检查高危路径规则，继续执行');
      return { canExecute: true, needConfirm: false, matchedRules: [], apiError: true };
    }
  };

  // Execute the actual file distribution
  const doExecute = async (values: { jobName: string; targetPath: string; timeout: string; overwriteStrategy: string }) => {
    const uploadResults = await Promise.all(
      localFiles.map((file) => uploadDistributionFile(file))
    );
    const fileIds = uploadResults.map((result) => result.id);

    // Convert HostItem to TargetListItem format
    const targetList = selectedHosts.map((h) => ({
      target_id: Number(h.key),
      name: h.hostName,
      ip: h.ipAddress,
      os: h.osType?.toLowerCase() as 'linux' | 'windows',
    }));

    await createFileDistribution({
      name: values.jobName,
      file_ids: fileIds,
      target_source: 'manual',
      target_list: targetList,
      target_path: values.targetPath,
      timeout: Number(values.timeout) || 600,
      overwrite_strategy: values.overwriteStrategy,
    });

    message.success(t('job.fileDistSuccess'));
    router.push('/job/execution/job-record');
  };

  const handleExecute = async () => {
    try {
      const values = await form.validateFields();

      if (selectedHosts.length === 0) {
        message.warning(t('job.addTargetHost'));
        return;
      }
      if (localFiles.length === 0) {
        message.warning(t('job.pleaseUploadFile'));
        return;
      }

      setSubmitting(true);

      // Check dangerous paths first
      console.log('[FileDistPage] Starting dangerous path check for:', values.targetPath);
      const checkResult = await checkDangerousPaths(values.targetPath);
      console.log('[FileDistPage] Check result:', checkResult);

      if (!checkResult.canExecute) {
        // Forbidden: show error and block execution
        Modal.error({
          title: t('job.dangerousPathDetected'),
          content: (
            <div>
              <p>{t('job.forbiddenPathMessage')}</p>
              <ul className="mt-2 list-disc pl-4">
                {checkResult.matchedRules.map((rule, idx) => (
                  <li key={idx} className="text-red-500 font-mono">{rule}</li>
                ))}
              </ul>
            </div>
          ),
          okText: t('common.confirm'),
        });
        setSubmitting(false);
        return;
      }

      if (checkResult.needConfirm) {
        // Confirm: show confirmation modal
        Modal.confirm({
          title: t('job.dangerousPathWarning'),
          icon: <ExclamationCircleOutlined style={{ color: '#faad14' }} />,
          content: (
            <div>
              <p>{t('job.confirmPathMessage')}</p>
              <ul className="mt-2 list-disc pl-4">
                {checkResult.matchedRules.map((rule, idx) => (
                  <li key={idx} className="text-orange-500 font-mono">{rule}</li>
                ))}
              </ul>
              <p className="mt-3 text-gray-500">{t('job.confirmExecuteQuestion')}</p>
            </div>
          ),
          okText: t('job.confirmExecute'),
          okButtonProps: { danger: true },
          cancelText: t('common.cancel'),
          onOk: async () => {
            try {
              await doExecute(values);
            } catch {
              // error handled by interceptor
            } finally {
              setSubmitting(false);
            }
          },
          onCancel: () => {
            setSubmitting(false);
          },
        });
        return;
      }

      // No dangerous paths: execute directly
      await doExecute(values);
    } catch {
      // validation or API error
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full h-full overflow-auto p-0">
      {/* Header */}
      <div
        className="rounded-lg px-6 py-4 mb-4"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2 className="text-base font-medium m-0 mb-1" style={{ color: 'var(--color-text-1)' }}>
          {t('job.fileDistTitle')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.fileDistDesc')}
        </p>
      </div>

      {/* Form */}
      <div
        className="rounded-lg px-6 py-6"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <Form
          form={form}
          layout="vertical"
          className="max-w-[720px]"
          initialValues={{ timeout: '600', overwriteStrategy: 'overwrite' }}
        >
          {/* 作业名称 */}
          <Form.Item
            label={t('job.jobName')}
            name="jobName"
            rules={[{ required: true, message: t('job.jobNamePlaceholder') }]}
          >
            <Input placeholder={t('job.jobNamePlaceholder')} />
          </Form.Item>

          {/* 目标主机 */}
          <Form.Item
            label={t('job.targetHost')}
            required
          >
            <div className="flex items-center gap-3">
              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => setHostModalOpen(true)}
              >
                {t('job.addTargetHost')}
              </Button>
              <span className="text-sm" style={{ color: 'var(--color-text-3)' }}>
                {t('job.selectedHosts').replace('{count}', String(selectedHosts.length))}
              </span>
            </div>
          </Form.Item>

          {/* 文件上传 */}
          <Form.Item
            label={t('job.fileUpload')}
            required
          >
            <Dragger
              multiple
              fileList={[]}
              beforeUpload={(file) => {
                setLocalFiles((prev) => [...prev, file]);
                return false;
              }}
              showUploadList={false}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">{t('job.fileUploadDrag')}</p>
              <p className="ant-upload-hint">{t('job.fileUploadHint')}</p>
            </Dragger>

            {/* Local file list */}
            {localFiles.length > 0 && (
              <div className="mt-3 flex flex-col gap-2">
                {localFiles.map((file, index) => (
                  <div
                    key={`${file.name}-${index}`}
                    className="flex items-center justify-between px-4 py-3 rounded-md"
                    style={{
                      border: '1px solid var(--color-border-1)',
                      background: 'var(--color-bg-2)',
                    }}
                  >
                    <div className="flex items-center gap-3">
                      <FileOutlined style={{ color: 'var(--color-text-3)', fontSize: 16 }} />
                      <div>
                        <div className="text-sm" style={{ color: 'var(--color-text-1)' }}>
                          {file.name}
                        </div>
                        <div className="text-xs" style={{ color: 'var(--color-text-3)' }}>
                          {formatFileSize(file.size)}
                        </div>
                      </div>
                    </div>
                    <CloseOutlined
                      className="cursor-pointer text-xs"
                      style={{ color: 'var(--color-text-3)' }}
                      onClick={() => handleRemoveFile(index)}
                    />
                  </div>
                ))}
              </div>
            )}
          </Form.Item>

          {/* 目标路径 */}
          <Form.Item
            label={t('job.fileDistTargetPath')}
            name="targetPath"
            rules={[{ required: true, message: t('job.fileDistTargetPathPlaceholder') }]}
          >
            <Input placeholder={t('job.fileDistTargetPathPlaceholder')} />
          </Form.Item>
          <p className="text-xs -mt-4 mb-6" style={{ color: 'var(--color-text-3)' }}>
            {t('job.fileDistTargetPathHint')}
          </p>

          {/* 覆盖策略 */}
          <Form.Item
            label={t('job.overwriteStrategy')}
            name="overwriteStrategy"
          >
            <Radio.Group>
              <Radio value="overwrite">{t('job.overwriteExisting')}</Radio>
              <Radio value="skip">{t('job.skipExisting')}</Radio>
            </Radio.Group>
          </Form.Item>

          {/* 超时时间 */}
          <Form.Item label={t('job.timeout')} name="timeout">
            <Input className="w-full" />
          </Form.Item>
          <p className="text-xs -mt-4 mb-6" style={{ color: 'var(--color-text-3)' }}>
            {t('job.fileDistTimeoutHint')}
          </p>

          <Divider />

          <Button
            type="primary"
            onClick={handleExecute}
            loading={submitting}
          >
            {t('job.executeNow')}
          </Button>
        </Form>
      </div>

      {/* Host Selection Modal */}
      <HostSelectionModal
        open={hostModalOpen}
        selectedKeys={selectedHostKeys}
        onConfirm={handleHostConfirm}
        onCancel={() => setHostModalOpen(false)}
      />
    </div>
  );
};

export default FileDistPage;
