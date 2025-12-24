'use client';
import React from 'react';
import { Drawer, Typography, Button, message } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { GraphNode } from '@/app/opspilot/types/knowledge';

const { Text } = Typography;

interface NodeDetailDrawerProps {
  visible: boolean;
  node: GraphNode | null;
  onClose: () => void;
}

/**
 * Node detail drawer component for displaying node information
 */
const NodeDetailDrawer: React.FC<NodeDetailDrawerProps> = ({ visible, node, onClose }) => {
  const { t } = useTranslation();

  const copyToClipboard = async (value: string) => {
    if (!value || value === '-') {
      message.warning('No content to copy');
      return;
    }

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
        message.success(t('common.copySuccess'));
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = value;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        textArea.style.top = '-9999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
          const successful = document.execCommand('copy');
          if (successful) {
            message.success(t('common.copySuccess'));
          } else {
            throw new Error('Copy command failed');
          }
        } catch (err) {
          console.error('Fallback copy failed:', err);
          message.error(t('common.copyFailed'));
        } finally {
          document.body.removeChild(textArea);
        }
      }
    } catch (error) {
      console.error('Copy to clipboard failed:', error);
      message.error(t('common.copyFailed'));
    }
  };

  const renderFieldRow = (label: string, value: string | number | undefined | null, index: number) => {
    const displayValue = value?.toString() || '-';
    const isEmpty = !value;
    const isEven = index % 2 === 0;
    
    return (
      <div 
        key={label}
        className={`flex items-center justify-between py-2 px-6 transition-all duration-200 hover:bg-blue-50 ${
          isEven ? 'bg-gray-50' : 'bg-white'
        }`}
      >
        <div className="flex items-center space-x-6 flex-1 min-w-0">
          <div className="w-24 flex-shrink-0">
            <Text className="text-xs font-semibold text-gray-700">{label}</Text>
          </div>
          <div className="flex-1 min-w-0">
            <Text 
              className={`text-xs ${isEmpty ? 'text-gray-400 italic' : 'text-gray-900'}`}
              style={{ 
                wordBreak: 'break-word',
                overflowWrap: 'break-word',
                lineHeight: '1.0'
              }}
            >
              {displayValue}
            </Text>
          </div>
        </div>
        <div className="flex-shrink-0 ml-4">
          <Button
            type="text"
            size="small"
            icon={<CopyOutlined />}
            onClick={() => copyToClipboard(displayValue)}
            title={t('common.copy')}
            className={`${isEmpty ? 'cursor-not-allowed text-gray-300' : 'text-blue-500 hover:text-blue-700 hover:bg-blue-100'} border-0 shadow-none transition-all duration-200`}
            disabled={isEmpty}
            style={{ 
              minWidth: '32px', 
              height: '32px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          />
        </div>
      </div>
    );
  };

  return (
    <Drawer
      title="Node Details"
      open={visible}
      onClose={onClose}
      width={680}
      placement="right"
    >
      {node && (
        <div className="bg-white rounded-md">
          <div className="border-t-0">
            {[
              { label: 'Name', value: node.name },
              { label: 'Summary', value: node.summary },
              { label: 'UUID', value: node.uuid },
              ...(node.labels && node.labels.length > 0 ? [{ label: 'Labels', value: node.labels.join(', ') }] : []),
              ...(node.fact ? [{ label: 'Fact', value: node.fact }] : [])
            ].map((field, index) => 
              renderFieldRow(field.label, field.value, index)
            )}
          </div>
        </div>
      )}
    </Drawer>
  );
};

export default NodeDetailDrawer;