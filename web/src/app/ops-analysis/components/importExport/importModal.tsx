import React, { useState } from 'react';
import {
  Modal,
  Upload,
  message,
  Spin,
  Steps,
  Button,
  Table,
  Radio,
  Alert,
  Typography,
  Input,
} from 'antd';
import {
  InboxOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleFilled,
} from '@ant-design/icons';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import {
  useImportExportApi,
  PrecheckResponse,
  ImportSubmitResponse,
  ConflictItem,
  ConflictDecision,
} from '../../api/importExport';
import {
  buildSecretSupplements,
  getSecretSupplementKey,
  getVisibleImportWarnings,
  hasBlockingImportWarnings,
  SECRET_PLACEHOLDER_WARNING_CODE,
  SecretSupplementValues,
} from './secretSupplements';
import type { UploadFile, UploadProps } from 'antd';

const { Dragger } = Upload;
const { Step } = Steps;
const { Text } = Typography;

export interface ImportModalProps {
  visible: boolean;
  onCancel: () => void;
  targetDirectoryId: number | null;
  onSuccess?: () => void | Promise<void>;
}

const ImportModal: React.FC<ImportModalProps> = ({
  visible,
  onCancel,
  targetDirectoryId,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { importPrecheck, importSubmit } = useImportExportApi();
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [precheckData, setPrecheckData] = useState<PrecheckResponse | null>(null);
  const [conflictDecisions, setConflictDecisions] = useState<Record<string, any>>({});
  const [secretSupplementValues, setSecretSupplementValues] = useState<SecretSupplementValues>({});
  const [submitResult, setSubmitResult] = useState<ImportSubmitResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [uploadKey, setUploadKey] = useState(0);

  const resetState = () => {
    setCurrentStep(0);
    setYamlContent('');
    setPrecheckData(null);
    setConflictDecisions({});
    setSecretSupplementValues({});
    setSubmitResult(null);
    setErrorMessage('');
    setFileList([]);
    setUploadKey((prev) => prev + 1);
  };

  const getObjectTypeLabel = (value: string) =>
    t(`opsAnalysisSidebar.objectTypeLabel.${value}`);

  const getConflictReasonLabel = (value: string) =>
    t(`opsAnalysisSidebar.conflictReasonLabel.${value}`);

  const handleClose = () => {
    resetState();
    onCancel();
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    maxCount: 1,
    showUploadList: false,
    fileList,
    beforeUpload: (file: File) => {
      const isYaml =
        file.name.endsWith('.yaml') ||
        file.name.endsWith('.yml') ||
        file.type === 'text/yaml' ||
        file.type === 'application/x-yaml';
      if (!isYaml) {
        message.error(t('opsAnalysisSidebar.importInvalidFileType'));
        return Upload.LIST_IGNORE;
      }
      const isLt2M = file.size / 1024 / 1024 < 2;
      if (!isLt2M) {
        message.error(t('opsAnalysisSidebar.importFileTooLarge'));
        return Upload.LIST_IGNORE;
      }
      return false;
    },
    onChange: async (info) => {
      setFileList(info.fileList);
      const file = info.fileList[0]?.originFileObj;
      if (!file) return;

      setLoading(true);
      setErrorMessage('');
      try {
        const text = await file.text();
        setYamlContent(text);
        setSecretSupplementValues({});
        const res = await importPrecheck({
          yaml_content: text,
          target_directory_id: targetDirectoryId,
        });

        if (!res.valid) {
          if (res.errors && res.errors.length > 0) {
            setErrorMessage(res.errors.map(e => e.message).join('; '));
          } else {
            setErrorMessage(t('opsAnalysisSidebar.importPrecheckFailed'));
          }
        } else {
          setPrecheckData(res);
          const initialDecisions: Record<string, any> = {};
          res.conflicts?.forEach((c) => {
            initialDecisions[c.object_key] = c.suggested_actions[0];
          });
          setConflictDecisions(initialDecisions);
          setCurrentStep(1);
        }
      } catch (err: any) {
        setErrorMessage(err?.message || t('opsAnalysisSidebar.importPrecheckError'));
        console.error('Import precheck error:', err);
      } finally {
        setLoading(false);
      }
    },
  };

  const handleSubmit = async () => {
    if (!yamlContent) return;

    setLoading(true);
    setErrorMessage('');
    try {
      const decisions: ConflictDecision[] = Object.keys(conflictDecisions).map((key) => ({
        object_key: key,
        action: conflictDecisions[key],
      }));

      const res = await importSubmit({
        yaml_content: yamlContent,
        target_directory_id: targetDirectoryId,
        conflict_decisions: decisions,
        secret_supplements: buildSecretSupplements(
          precheckData?.warnings || [],
          conflictDecisions,
          secretSupplementValues,
        ),
      });

      if (res.success) {
        setSubmitResult(res);
        setCurrentStep(2);
        setFileList([]);
        setUploadKey((prev) => prev + 1);
        if (onSuccess) {
          await onSuccess();
        }
      } else {
        setErrorMessage(t('opsAnalysisSidebar.importSubmitFailed'));
      }
    } catch (err: any) {
      setErrorMessage(err?.message || t('opsAnalysisSidebar.importSubmitError'));
      console.error('Import submit error:', err);
    } finally {
      setLoading(false);
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <div className="py-8">
            <Spin spinning={loading}>
              <Dragger key={uploadKey} {...uploadProps}>
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">
                  {t('opsAnalysisSidebar.importUploadText')}
                </p>
                <p className="ant-upload-hint text-gray-400 mt-2">
                  {t('opsAnalysisSidebar.importUploadHint')}
                </p>
              </Dragger>
            </Spin>
            {errorMessage && (
              <Alert message={errorMessage} type="error" showIcon className="mt-4" />
            )}
          </div>
        );

      case 1: {
        const columns = [
          {
            title: t('opsAnalysisSidebar.objectName'),
            dataIndex: 'object_key',
            key: 'object_key',
            width: '34%',
            render: (value: string) => (
              <EllipsisWithTooltip
                text={value}
                className="block w-full overflow-hidden text-ellipsis whitespace-nowrap"
              />
            ),
          },
          {
            title: t('opsAnalysisSidebar.objectType'),
            dataIndex: 'object_type',
            key: 'object_type',
            width: '14%',
            render: (value: string) => getObjectTypeLabel(value),
          },
          {
            title: t('opsAnalysisSidebar.conflictReason'),
            dataIndex: 'reason',
            key: 'reason',
            width: '14%',
            render: (value: string) => getConflictReasonLabel(value),
          },
          {
            title: t('opsAnalysisSidebar.conflictAction'),
            key: 'action',
            width: '38%',
            render: (_: any, record: ConflictItem) => (
              <Radio.Group
                className="flex items-center whitespace-nowrap"
                value={conflictDecisions[record.object_key]}
                onChange={(e) =>
                  setConflictDecisions({
                    ...conflictDecisions,
                    [record.object_key]: e.target.value,
                  })
                }
              >
                {record.suggested_actions.includes('skip') && (
                  <Radio value="skip" className="mr-3">{t('opsAnalysisSidebar.actionSkip')}</Radio>
                )}
                {record.suggested_actions.includes('overwrite') && (
                  <Radio value="overwrite" className="mr-3">{t('opsAnalysisSidebar.actionOverwrite')}</Radio>
                )}
                {record.suggested_actions.includes('rename') && (
                  <Radio value="rename">{t('opsAnalysisSidebar.actionRename')}</Radio>
                )}
              </Radio.Group>
            ),
          },
        ];

        const filteredWarnings = getVisibleImportWarnings(
          precheckData?.warnings || [],
          conflictDecisions,
        );
        const hasBlockingWarnings = hasBlockingImportWarnings(
          precheckData?.warnings || [],
          conflictDecisions,
          secretSupplementValues,
        );

        return (
          <div className="py-4">
            {errorMessage && (
              <Alert message={errorMessage} type="error" showIcon className="mb-4" />
            )}
            
            {filteredWarnings.length > 0 && (
              <div className="mb-4 rounded-lg border border-[#FFD591] bg-[#FFFBE6] px-5 py-4">
                <div className="flex items-start gap-2">
                  <ExclamationCircleFilled
                    className="mt-1 text-base leading-none text-[#FAAD14]"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium leading-6 text-[rgba(0,0,0,0.88)]">
                      {t('opsAnalysisSidebar.importWarnings')}
                    </div>
                    <ul className="mt-1 mb-0 text-sm leading-6 text-[rgba(0,0,0,0.65)]">
                      {filteredWarnings.map((w, idx) => {
                        const supplementKey = getSecretSupplementKey(w);
                        const isSecretPlaceholder = (
                          w.code === SECRET_PLACEHOLDER_WARNING_CODE && supplementKey
                        );
                        const isOverwrite = (
                          !!w.object_key && conflictDecisions[w.object_key] === 'overwrite'
                        );

                        return (
                          <li key={supplementKey || idx} className="mb-2 last:mb-0">
                            <div>{w.message}</div>
                            {isSecretPlaceholder && (
                              <Input.Password
                                className="mt-1 max-w-xl"
                                value={secretSupplementValues[supplementKey] || ''}
                                onChange={(event) => setSecretSupplementValues((current) => ({
                                  ...current,
                                  [supplementKey]: event.target.value,
                                }))}
                                placeholder={t(
                                  isOverwrite
                                    ? 'opsAnalysisSidebar.importSecretOverwritePlaceholder'
                                    : 'opsAnalysisSidebar.importSecretPlaceholder',
                                )}
                                aria-label={`${w.object_key} ${w.field}`}
                                autoComplete="new-password"
                              />
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            <div className="mb-4 flex flex-wrap gap-x-4 gap-y-2 text-gray-600">
              <span>{t('opsAnalysisSidebar.totalObjects')} {precheckData?.counts.total || 0}</span>
              {precheckData?.counts.by_type && Object.entries(precheckData.counts.by_type).map(([k, v]) => (
                v > 0 ? <span key={k}>{getObjectTypeLabel(k)}: {v}</span> : null
              ))}
            </div>

            {precheckData?.conflicts && precheckData.conflicts.length > 0 ? (
              <>
                <Text strong className="block mb-2">
                  {t('opsAnalysisSidebar.resolveConflicts')}
                </Text>
                <Table
                  dataSource={precheckData.conflicts}
                  columns={columns}
                  rowKey="object_key"
                  pagination={false}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ y: 300 }}
                />
              </>
            ) : (
              <Alert
                message={t('opsAnalysisSidebar.precheckPass')}
                type="success"
                showIcon
              />
            )}
            
            <div className="mt-6 flex justify-end gap-2">
              <Button onClick={() => setCurrentStep(0)} disabled={loading}>
                {t('opsAnalysisSidebar.reupload')}
              </Button>
              <Button
                type="primary"
                onClick={handleSubmit}
                loading={loading}
                disabled={hasBlockingWarnings}
              >
                {t('opsAnalysisSidebar.startImport')}
              </Button>
            </div>
          </div>
        );
      }

      case 2: {
        if (!submitResult) return null;

        const resultColumns = [
          {
            title: t('opsAnalysisSidebar.objectName'),
            dataIndex: 'object_key',
            key: 'object_key',
            render: (value: string) => (
              <EllipsisWithTooltip
                text={value}
                className="block w-full overflow-hidden text-ellipsis whitespace-nowrap"
              />
            ),
          },
          {
            title: t('opsAnalysisSidebar.objectType'),
            dataIndex: 'object_type',
            key: 'object_type',
            render: (value: string) => getObjectTypeLabel(value),
          },
          {
            title: t('opsAnalysisSidebar.status'),
            dataIndex: 'status',
            key: 'status',
            render: (status: string) => {
              if (status === 'success') return <Text type="success"><CheckCircleOutlined className="mr-1"/>{t('opsAnalysisSidebar.statusSuccess')}</Text>;
              if (status === 'failed') return <Text type="danger"><CloseCircleOutlined className="mr-1"/>{t('opsAnalysisSidebar.statusFailed')}</Text>;
              if (status === 'skipped') return <Text type="secondary">{t('opsAnalysisSidebar.statusSkipped')}</Text>;
              if (status === 'overwritten') return <Text type="warning">{t('opsAnalysisSidebar.statusOverwritten')}</Text>;
              return status;
            },
          },
          {
            title: t('opsAnalysisSidebar.message'),
            dataIndex: 'message',
            key: 'message',
            render: (value: string) => (
              <EllipsisWithTooltip
                text={value}
                className="block w-full overflow-hidden text-ellipsis whitespace-nowrap"
              />
            ),
          },
        ];

        return (
          <div className="py-4">
            <Alert
              message={t('opsAnalysisSidebar.importResultSummary')}
              description={
                <div className="flex gap-4">
                  <span>{t('opsAnalysisSidebar.totalCount')} {submitResult.summary.total}</span>
                  <span className="text-green-600">{t('opsAnalysisSidebar.successCount')} {submitResult.summary.success}</span>
                  <span className="text-yellow-600">{t('opsAnalysisSidebar.overwrittenCount')} {submitResult.summary.overwritten}</span>
                  <span className="text-gray-500">{t('opsAnalysisSidebar.skippedCount')} {submitResult.summary.skipped}</span>
                  <span className="text-red-600">{t('opsAnalysisSidebar.failedCount')} {submitResult.summary.failed}</span>
                </div>
              }
              type="success"
              showIcon
              className="mb-4"
            />
            
            <Table
              dataSource={submitResult.results}
              columns={resultColumns}
              rowKey="object_key"
              pagination={false}
              size="small"
              scroll={{ y: 300 }}
            />
            
            <div className="mt-6 flex justify-end">
              <Button type="primary" onClick={handleClose}>
                {t('common.close')}
              </Button>
            </div>
          </div>
        );
      }

      default:
        return null;
    }
  };

  return (
    <Modal
      title={t('opsAnalysisSidebar.importYaml')}
      open={visible}
      onCancel={handleClose}
      footer={null}
      width={700}
      destroyOnHidden
      centered
      maskClosable={false}
    >
      <div className="pt-2">
        <Steps current={currentStep} size="small" className="mb-4">
          <Step title={t('opsAnalysisSidebar.stepUpload')} />
          <Step title={t('opsAnalysisSidebar.stepPrecheck')} />
          <Step title={t('opsAnalysisSidebar.stepResult')} />
        </Steps>
        {renderStepContent()}
      </div>
    </Modal>
  );
};

export default ImportModal;
