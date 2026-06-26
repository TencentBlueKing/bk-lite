'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Input, Spin, Tooltip } from 'antd';
import {
  CloseOutlined,
  CommentOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  RobotOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiQaResult } from '@/app/opspilot/types/wiki';
import { WikiCitation } from '@/app/opspilot/types/global';
import WikiCitations from '@/app/opspilot/components/custom-chat-sse/WikiCitations';

interface Msg {
  role: 'user' | 'bot';
  text: string;
  citations?: WikiCitation[];
}

// 知识库问答助手:默认仅右下悬浮按钮,点击展开对话弹窗(可全屏),用知识库 qa 接口逐轮问答。
const WikiQaAssistant: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { qa } = useWikiApi();
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setMessages((m) => [...m, { role: 'user', text: q }]);
    setLoading(true);
    try {
      const res: WikiQaResult = await qa(kbId, q);
      setMessages((m) => [...m, { role: 'bot', text: res.answer, citations: res.citations }]);
    } catch {
      setMessages((m) => [...m, { role: 'bot', text: t('wiki.qaError') }]);
    } finally {
      setLoading(false);
    }
  };

  const close = () => {
    setOpen(false);
    setFullscreen(false);
  };

  return (
    <>
      {/* 悬浮按钮(默认状态) */}
      {!open && (
        <Tooltip title={t('wiki.assistant')} placement="left">
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="fixed bottom-6 right-6 z-[900] flex h-14 w-14 items-center justify-center rounded-full bg-[var(--color-primary)] text-white shadow-lg transition-transform hover:scale-105"
            aria-label={t('wiki.assistant')}
          >
            <RobotOutlined style={{ fontSize: 24 }} />
          </button>
        </Tooltip>
      )}

      {/* 对话弹窗 */}
      {open && (
        <div
          className={
            fullscreen
              ? 'fixed inset-0 z-[1000] flex flex-col bg-[var(--color-bg-1)]'
              : 'fixed bottom-6 right-6 z-[1000] flex h-[560px] max-h-[calc(100vh-48px)] w-[400px] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-xl border border-[var(--color-border-1)] bg-[var(--color-bg-1)] shadow-2xl'
          }
        >
          {/* 头部 */}
          <div className="flex items-center justify-between border-b border-[var(--color-border-1)] px-4 py-3">
            <span className="flex items-center gap-2 font-medium text-[var(--color-text-1)]">
              <RobotOutlined className="text-[var(--color-primary)]" />
              {t('wiki.assistant')}
            </span>
            <div className="flex items-center gap-3 text-[var(--color-text-3)]">
              <Tooltip title={fullscreen ? t('wiki.exitFullscreen') : t('wiki.fullscreen')}>
                <span className="cursor-pointer hover:text-[var(--color-text-1)]" onClick={() => setFullscreen((v) => !v)}>
                  {fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                </span>
              </Tooltip>
              <span className="cursor-pointer hover:text-[var(--color-text-1)]" onClick={close}>
                <CloseOutlined />
              </span>
            </div>
          </div>

          {/* 消息区 */}
          <div ref={listRef} className="flex-1 overflow-auto px-4 py-3">
            {messages.length === 0 && !loading ? (
              <div className="flex h-full flex-col items-center justify-center text-[var(--color-text-3)]">
                <CommentOutlined style={{ fontSize: 40 }} className="mb-3 opacity-40" />
                <span className="text-sm">{t('wiki.qaEmpty')}</span>
              </div>
            ) : (
              <div className={`mx-auto space-y-3 ${fullscreen ? 'max-w-3xl' : ''}`}>
                {messages.map((m, i) => (
                  <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                    <div
                      className={
                        m.role === 'user'
                          ? 'max-w-[80%] rounded-lg rounded-br-sm bg-[var(--color-primary)] px-3 py-2 text-sm text-white'
                          : 'max-w-[85%] rounded-lg rounded-bl-sm bg-[var(--color-fill-1)] px-3 py-2 text-sm text-[var(--color-text-1)]'
                      }
                    >
                      <p className="m-0 whitespace-pre-wrap break-words">{m.text}</p>
                      {!!m.citations?.length && <WikiCitations citations={m.citations} content={m.text} />}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex justify-start">
                    <div className="rounded-lg bg-[var(--color-fill-1)] px-4 py-2">
                      <Spin size="small" />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 输入区 */}
          <div className="flex items-end gap-2 border-t border-[var(--color-border-1)] p-3">
            <Input.TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={t('wiki.qaPlaceholder')}
              autoSize={{ minRows: 1, maxRows: 4 }}
              className="flex-1"
            />
            <Button
              type="primary"
              shape="circle"
              loading={loading}
              icon={<SendOutlined />}
              onClick={send}
              disabled={!input.trim()}
            />
          </div>
        </div>
      )}
    </>
  );
};

export default WikiQaAssistant;
