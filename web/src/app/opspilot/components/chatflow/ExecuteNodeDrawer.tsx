'use client';

import React, { useEffect, useMemo } from 'react';
import { Drawer, Form, Input, Button, Typography, Alert } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { NodeExecutionResult } from './hooks/useNodeExecution';
import { ToolCallInfo, initToolCallTooltips, renderToolCallCard } from '../custom-chat-sse/toolCallRenderer';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';
import styles from '../custom-chat/index.module.scss';

const { TextArea } = Input;
const { Text } = Typography;

const md = new MarkdownIt({
  html: true,
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch {}
    }
    return '';
  },
});

interface ExecuteNodeDrawerProps {
  visible: boolean;
  nodeId: string;
  message: string;
  result: NodeExecutionResult | null;
  loading: boolean;
  streamingContent: string;
  onMessageChange: (message: string) => void;
  onExecute: () => void;
  onClose: () => void;
  onStop?: () => void;
}

const ExecuteNodeDrawer: React.FC<ExecuteNodeDrawerProps> = ({
  visible,
  nodeId,
  message,
  result,
  loading,
  streamingContent,
  onMessageChange,
  onExecute,
  onClose,
  onStop
}) => {
  const { t } = useTranslation();

  useEffect(() => {
    if (visible && typeof window !== 'undefined') {
      initToolCallTooltips();
    }
  }, [visible]);

  const renderToolCalls = (toolCalls?: Map<string, ToolCallInfo>) => {
    if (!toolCalls || toolCalls.size === 0) return null;
    
    const toolCallsHtml = Array.from(toolCalls.entries())
      .map(([id, info]) => renderToolCallCard(id, info))
      .join('');

    return (
      <div 
        className="mb-3"
        dangerouslySetInnerHTML={{ __html: toolCallsHtml }}
      />
    );
  };

  const renderedContent = useMemo(() => {
    const content = result?.content || streamingContent;
    if (!content) return '';
    return md.render(content);
  }, [result?.content, streamingContent]);

  const renderSSEResult = () => {
    const content = result?.content || streamingContent;
    const hasContent = content || (result?.toolCalls && result.toolCalls.size > 0);
    
    if (!hasContent && !loading) return null;

    return (
      <div className="mt-4">
        <h3 className="mb-2 font-medium">{t('chatflow.executeResult')}</h3>
        <div className="bg-[var(--color-fill-1)] p-4 rounded-md">
          {renderToolCalls(result?.toolCalls)}
          
          {content && (
            <div
              dangerouslySetInnerHTML={{ __html: renderedContent }}
              className={styles.markdownBody}
            />
          )}
          
          {loading && !content && !result?.toolCalls?.size && (
            <div className="flex items-center gap-2 text-[var(--color-text-3)]">
              <span className="inline-flex gap-1">
                <span className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
              </span>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderJSONResult = () => {
    if (!result || result.isSSE) return null;

    return (
      <div className="mt-4">
        <h3 className="mb-2 font-medium">{t('chatflow.executeResult')}</h3>
        <div className="bg-[var(--color-fill-1)] p-4 rounded-md">
          <pre className="whitespace-pre-wrap text-sm overflow-auto max-h-60 font-mono">
            {JSON.stringify(result.rawResponse?.content ?? result.rawResponse, null, 2)}
          </pre>
        </div>
      </div>
    );
  };

  const renderError = () => {
    if (!result?.error) return null;

    return (
      <Alert
        className="mt-4"
        type="error"
        message={t('chatflow.executeFailed')}
        description={result.error}
        showIcon
      />
    );
  };

  const renderResult = () => {
    if (result?.error) {
      return renderError();
    }

    if (result?.isSSE || loading || streamingContent) {
      return renderSSEResult();
    }

    if (result && !result.isSSE) {
      return renderJSONResult();
    }

    return null;
  };

  return (
    <Drawer
      title={t('chatflow.executeNode')}
      open={visible}
      onClose={onClose}
      width={520}
      placement="right"
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>
            {t('common.cancel')}
          </Button>
          {loading && onStop ? (
            <Button onClick={onStop} danger>
              {t('common.stop')}
            </Button>
          ) : (
            <Button 
              type="primary" 
              onClick={onExecute}
              loading={loading}
            >
              {t('common.execute')}
            </Button>
          )}
        </div>
      }
    >
      <div>
        <div className="mb-4">
          <Text type="secondary">
            {t('chatflow.nodeConfig.nodeName')}: {nodeId}
          </Text>
        </div>

        <Form layout="vertical">
          <Form.Item 
            label={t('chatflow.executeMessage')}
          >
            <TextArea
              rows={4}
              value={message}
              onChange={(e) => onMessageChange(e.target.value)}
              placeholder={t('chatflow.executeMessagePlaceholder')}
              disabled={loading}
            />
          </Form.Item>
        </Form>

        {renderResult()}
      </div>
    </Drawer>
  );
};

export default ExecuteNodeDrawer;
