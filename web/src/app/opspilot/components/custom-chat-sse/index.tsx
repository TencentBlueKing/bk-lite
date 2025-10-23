import React, { useState, useCallback, useRef, ReactNode, useEffect } from 'react';
import { Popconfirm, Button, Tooltip, Flex, Spin, Drawer, ButtonProps } from 'antd';
import { FullscreenOutlined, FullscreenExitOutlined, SendOutlined } from '@ant-design/icons';
import { Bubble, Sender } from '@ant-design/x';
import { v4 as uuidv4 } from 'uuid';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/atom-one-dark.css';
import styles from '../custom-chat/index.module.scss';
import MessageActions from '../custom-chat/actions';
import KnowledgeBase from '../custom-chat/knowledgeBase';
import AnnotationModal from '../custom-chat/annotationModal';
import KnowledgeGraphView from '../knowledge/knowledgeGraphView';
import PermissionWrapper from '@/components/permission';
import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';
import { useSession } from 'next-auth/react';
import { useAuth } from '@/context/auth';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import { transformGraphData } from '@/app/opspilot/utils/graphUtils';
import {
  CustomChatSSEProps,
  ActionRender,
  SSEChunk,
  ReferenceModalState,
  DrawerContentState,
  GuideParseResult
} from '@/app/opspilot/types/chat';

const md = new MarkdownIt({
  html: true,
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch { }
    }
    return '';
  },
});

const CustomChatSSE: React.FC<CustomChatSSEProps> = ({ 
  handleSendMessage, 
  showMarkOnly = false, 
  initialMessages = [], 
  mode = 'chat',
  guide
}) => {
  const { t } = useTranslation();
  
  let session = null;
  try {
    const sessionData = useSession();
    session = sessionData.data;
  } catch (error) {
    console.warn('useSession hook error, falling back to auth context:', error);
  }
  
  const authContext = useAuth();
  const token = session?.user?.token || authContext?.token || null;

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [value, setValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<CustomChatMessage[]>(initialMessages.length ? initialMessages : []);
  const [annotationModalVisible, setAnnotationModalVisible] = useState(false);
  const [annotation, setAnnotation] = useState<Annotation | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentBotMessageRef = useRef<CustomChatMessage | null>(null);
  const chatContentRef = useRef<HTMLDivElement>(null);

  const [referenceModal, setReferenceModal] = useState<ReferenceModalState>({
    visible: false,
    loading: false,
    title: '',
    content: ''
  });

  const [drawerContent, setDrawerContent] = useState<DrawerContentState>({
    visible: false,
    title: '',
    content: '',
    chunkType: undefined,
    graphData: undefined
  });

  const { getChunkDetail } = useKnowledgeApi();

  // Auto scroll to bottom function
  const scrollToBottom = useCallback(() => {
    if (chatContentRef.current) {
      const element = chatContentRef.current;
      // Use smooth scrolling for better user experience
      element.scrollTo({
        top: element.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, []);

  // Auto scroll when messages change or during streaming
  useEffect(() => {
    // Only auto scroll when there are messages and either loading or new messages added
    if (messages.length > 0) {
      // Use requestAnimationFrame to ensure DOM has been updated
      requestAnimationFrame(() => {
        scrollToBottom();
      });
    }
  }, [messages]);

  // Parse guide text and extract content within [] as quick send items
  const parseGuideItems = useCallback((guideText: string): GuideParseResult => {
    if (!guideText) return { text: '', items: [], renderedHtml: '' };
    
    const regex = /\[([^\]]+)\]/g;
    const items: string[] = [];
    let match;
    
    // Extract all content within []
    while ((match = regex.exec(guideText)) !== null) {
      items.push(match[1]);
    }
    
    // Preserve line breaks, convert newlines to <br> tags first, then process [] content
    const processedText = guideText.replace(/\n/g, '<br>');
    
    // Convert [] content to clickable HTML elements
    const renderedHtml = processedText.replace(regex, (match, content) => {
      return `<span class="guide-clickable-item" data-content="${content}" style="color: #1890ff; cursor: pointer; font-weight: 600; margin: 0 2px;">${content}</span>`;
    });
    
    return { text: guideText, items, renderedHtml };
  }, []);

  // Parse and handle reference links in content
  const parseReferenceLinks = useCallback((content: string) => {
    // Match pattern like [[48]](chunk_id:3444444|knowledge_id:4555|chunk_type:Document/QA/Graph)
    const referenceRegex = /\[\[(\d+)\]\]\(([^)]+)\)/g;
    // console.log('Parsing references in content:', content);
    
    return content.replace(referenceRegex, (match, refNumber, params) => {
      // Parse parameters from the link using | as separator
      const paramPairs = params.split('|');
      const urlParams = new Map();
      
      paramPairs.forEach((pair: string) => {
        const [key, value] = pair.split(':');
        if (key && value) {
          urlParams.set(key, value);
        }
      });
      
      const chunkId = urlParams.get('chunk_id');
      const knowledgeId = urlParams.get('knowledge_id');
      const chunkType = urlParams.get('chunk_type') || 'Document';
      
      const getIconType = (type: string) => {
        switch (type) {
          case 'Document':
            return 'wendangguanlixitong-wendangguanlixitongtubiao';
          case 'QA':
            return 'wendaduihua';
          case 'Graph':
            return 'zhishitupu';
          default:
            return 'wendangguanlixitong-wendangguanlixitongtubiao';
        }
      };
      
      const iconType = getIconType(chunkType);
      
      // Create a clickable span with data attributes and embedded SVG icon
      return `<span class="reference-link inline-flex items-center gap-1" 
                data-ref-number="${refNumber}" 
                data-chunk-id="${chunkId}" 
                data-knowledge-id="${knowledgeId}"
                data-chunk-type="${chunkType}"
                style="color: #1890ff; cursor: pointer; margin: 0 2px;">
                <svg class="icon icon-${iconType} inline-block" style="width: 1em; height: 1em; vertical-align: text-bottom;" aria-hidden="true">
                  <use href="#icon-${iconType}"></use>
                </svg>
              </span>`;
    });
  }, []);

  // Parse and handle suggestion links in content
  const parseSuggestionLinks = useCallback((content: string) => {
    // Match pattern like [1](suggest:xxxxx) or [2](suggest: xxx)
    const suggestionRegex = /\[(\d+)\]\(suggest:\s*([^)]+)\)/g;
    
    return content.replace(suggestionRegex, (match, number, suggestionText) => {
      const trimmedText = suggestionText.trim();
      
      // Create a button-style clickable element using Tailwind classes
      return `<button class="suggestion-button inline-block text-[var(--color-text-1)] text-left border border-[var(--color-border-1)] rounded-full px-3 py-1.5 mx-1 my-1 cursor-pointer text-xs transition-all duration-200 ease-in-out hover:shadow-md hover:-translate-y-0.5 hover:border-blue-400 active:scale-95" 
                data-suggestion="${trimmedText}">
                ${trimmedText}
              </button>`;
    });
  }, []);

  // 通用的发送消息处理逻辑
  const handleClickableItemSend = useCallback(async (content: string) => {
    if (!content || loading || !token) {
      return;
    }

    // console.log('Clicking item with content:', content);
    
    setLoading(true);
    
    // Create user message
    const newUserMessage: CustomChatMessage = {
      id: uuidv4(),
      content,
      role: 'user',
      createAt: new Date().toISOString(),
      updateAt: new Date().toISOString(),
    };

    // console.log('Created user message:', newUserMessage);

    // Create bot loading message
    const botLoadingMessage: CustomChatMessage = {
      id: uuidv4(),
      content: '',
      role: 'bot',
      createAt: new Date().toISOString(),
      updateAt: new Date().toISOString(),
    };

    // Get current message state first, then immediately update UI
    const currentMessages = messages;
    const updatedMessages = [...currentMessages, newUserMessage, botLoadingMessage];
    updateMessages(updatedMessages);
    currentBotMessageRef.current = botLoadingMessage;

    // Execute sending logic asynchronously
    try {
      if (handleSendMessage) {
        const result = await handleSendMessage(content, currentMessages);
        
        if (result === null) {
          updateMessages(currentMessages);
          setLoading(false);
          return;
        }
        
        const { url, payload } = result;
        await handleSSEStream(url, payload, botLoadingMessage);
      }
    } catch (error: any) {
      console.error(`${t('chat.sendFailed')}:`, error);
      
      updateMessages(prevMessages => 
        prevMessages.map(msgItem => 
          msgItem.id === botLoadingMessage.id 
            ? { ...msgItem, content: t('chat.connectionError') }
            : msgItem
        )
      );
      setLoading(false);
    }
  }, [loading, token, messages, handleSendMessage]);

  // Handle click events for clickable elements in guide text
  const handleGuideClick = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.classList.contains('guide-clickable-item')) {
      const content = target.getAttribute('data-content');
      if (content) {
        handleClickableItemSend(content);
      }
    }
  }, [handleClickableItemSend]);

  // Handle reference link click
  const handleReferenceClick = useCallback(async (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    
    let referenceElement = target;
    while (referenceElement && !referenceElement.classList.contains('reference-link')) {
      referenceElement = referenceElement.parentElement as HTMLElement;
    }
    
    if (referenceElement && referenceElement.classList.contains('reference-link')) {
      const chunkId = referenceElement.getAttribute('data-chunk-id');
      const knowledgeId = referenceElement.getAttribute('data-knowledge-id');
      const chunkType = referenceElement.getAttribute('data-chunk-type') || 'Document';
            
      if (!knowledgeId) {
        console.warn('Missing knowledge_id in reference link');
        return;
      }

      setDrawerContent({
        visible: true,
        title: `${t('chat.chunkDetails')}`,
        content: '',
        chunkType: chunkType as "Document" | "QA" | "Graph",
        graphData: undefined
      });

      setReferenceModal(prev => ({
        ...prev,
        loading: true
      }));

      try {
        // Use type parameter instead of is_qa_pairs
        // QA type uses 'QA', other types (Document/Graph) use their respective values
        const data = await getChunkDetail(knowledgeId, chunkId, chunkType as "Document" | "QA" | "Graph" | undefined);
        
        if (chunkType === 'Graph' && data) {
          // For Graph type, prepare graph data
          let graphData: { nodes: any[], edges: any[] } = { nodes: [], edges: [] };
          
          // data is already the graph data array from getChunkDetail API
          if (Array.isArray(data)) {
            graphData = transformGraphData(data);
          } else if (data.content) {
            // Fallback: try to parse content as JSON for graph data
            try {
              const parsedContent = JSON.parse(data.content);
              if (Array.isArray(parsedContent)) {
                graphData = transformGraphData(parsedContent);
              } else if (parsedContent.nodes && parsedContent.edges) {
                graphData = parsedContent;
              }
            } catch (e) {
              console.warn('Failed to parse graph data from content:', e);
            }
          }
          
          setDrawerContent(prev => ({
            ...prev,
            graphData: graphData
          }));
        } else {
          // For Document and QA types, handle as before
          let displayContent = '';
          
          if (chunkType === 'QA' && data) {
            // For QA pairs, format as Question: xxx, Answer: xxx
            const question = data.question || '';
            const answer = data.answer || '';
            displayContent = `问题：${question}\n\n答案：${answer}`;
          } else {
            // For Document type, use content directly
            displayContent = data?.content || '--';
          }
          
          setDrawerContent(prev => ({
            ...prev,
            content: displayContent
          }));
        }
      } catch (error) {
        console.error('Failed to fetch reference details:', error);
      } finally {
        setReferenceModal(prev => ({
          ...prev,
          loading: false
        }));
      }
    }
  }, []);

  // Handsuggestion button click
  const handleSuggestionClick = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (target.classList.contains('suggestion-button')) {
      const suggestionText = target.getAttribute('data-suggestion');
      if (suggestionText) {
        handleClickableItemSend(suggestionText);
      }
    }
  }, [handleClickableItemSend]);

  const handleFullscreenToggle = () => {
    setIsFullscreen(!isFullscreen);
  };

  const handleClearMessages = () => {
    // Stop any ongoing SSE connections
    stopSSEConnection();
    // Clear message array
    updateMessages([]);
    // Reset current bot message reference
    currentBotMessageRef.current = null;
  };

  const stopSSEConnection = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLoading(false);
  }, []);

  const updateMessages = useCallback((newMessages: CustomChatMessage[] | ((prev: CustomChatMessage[]) => CustomChatMessage[])) => {
    setMessages(prevMessages => {
      const updatedMessages = typeof newMessages === 'function' ? newMessages(prevMessages) : newMessages;
      
      // Trigger auto scroll after state update
      setTimeout(() => {
        scrollToBottom();
      }, 50);
      
      return updatedMessages;
    });
  }, []);

  // Handle SSE streaming response
  const handleSSEStream = useCallback(async (url: string, payload: any, botMessage: CustomChatMessage) => {
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      // Use simplified request headers to avoid 406 errors
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      // Only add Authorization header when token exists
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        credentials: 'include',
        signal: abortController.signal,
      });

      if (!response.ok) {
        console.error(`HTTP ${response.status}: ${response.statusText}`);
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Failed to get response reader');
      }

      const decoder = new TextDecoder();
      let accumulatedContent = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;
        
        // Process data line by line
        const lines = buffer.split('\n');
        // Keep the last line (might be incomplete)
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (trimmedLine === '') continue;
          
          // Process SSE data lines
          if (trimmedLine.startsWith('data: ')) {
            const dataStr = trimmedLine.slice(6).trim();
            
            // Check for end marker
            if (dataStr === '[DONE]') {
              console.log('SSE stream completed with [DONE]');
              setLoading(false);
              return;
            }

            try {
              const sseData: SSEChunk = JSON.parse(dataStr);
              
              // Process streaming content
              if (sseData.choices && sseData.choices.length > 0) {
                const choice = sseData.choices[0];
                
                // Check if completed
                if (choice.finish_reason === 'stop') {
                  console.log('SSE stream completed with finish_reason: stop');
                  setLoading(false);
                  return;
                }

                // Accumulate content
                if (choice.delta && choice.delta.content) {
                  accumulatedContent += choice.delta.content;
                  
                  // Update message content in real-time with auto scroll
                  updateMessages(prevMessages => 
                    prevMessages.map(msgItem => 
                      msgItem.id === botMessage.id 
                        ? { 
                          ...msgItem, 
                          content: accumulatedContent,
                          updateAt: new Date().toISOString()
                        }
                        : msgItem
                    )
                  );
                }
              }
            } catch (parseError) {
              console.warn('Failed to parse SSE chunk:', dataStr, parseError);
              continue;
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('SSE connection aborted');
        return;
      }
      
      console.error('SSE stream error:', error);
      
      // Update error message
      updateMessages(prevMessages => 
        prevMessages.map(msgItem => 
          msgItem.id === botMessage.id 
            ? { ...msgItem, content: `${t('chat.connectionError')}: ${error.message}` }
            : msgItem
        )
      );
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  }, [token, updateMessages]);

  const handleSend = useCallback(async (msg: string) => {
    if (msg.trim() && !loading && token) {
      setLoading(true);
      
      // Create user message
      const newUserMessage: CustomChatMessage = {
        id: uuidv4(),
        content: msg,
        role: 'user',
        createAt: new Date().toISOString(),
        updateAt: new Date().toISOString(),
      };

      // Create bot loading message
      const botLoadingMessage: CustomChatMessage = {
        id: uuidv4(),
        content: '',
        role: 'bot',
        createAt: new Date().toISOString(),
        updateAt: new Date().toISOString(),
      };

      // Get messages currently displayed in the dialog as history
      const currentDisplayedMessages = messages;
      const updatedMessages = [...currentDisplayedMessages, newUserMessage, botLoadingMessage];
      updateMessages(updatedMessages);
      currentBotMessageRef.current = botLoadingMessage;

      try {
        if (handleSendMessage) {
          // Pass messages currently displayed in the dialog as history
          const result = await handleSendMessage(msg, currentDisplayedMessages);
          
          // If handleSendMessage returns null, form validation failed, prevent sending
          if (result === null) {
            // Remove added messages
            updateMessages(currentDisplayedMessages);
            setLoading(false);
            return;
          }
          
          const { url, payload } = result;
          await handleSSEStream(url, payload, botLoadingMessage);
        }
      } catch (error: any) {
        console.error(`${t('chat.sendFailed')}:`, error);
        
        updateMessages(prevMessages => 
          prevMessages.map(msgItem => 
            msgItem.id === botLoadingMessage.id 
              ? { ...msgItem, content: t('chat.connectionError') }
              : msgItem
          )
        );
        setLoading(false);
      }
    }
  }, [loading, messages, token, handleSendMessage, handleSSEStream, updateMessages]);

  const handleCopyMessage = (content: string) => {
    navigator.clipboard.writeText(content).then(() => {
      console.log(t('chat.copied'));
    }).catch(err => {
      console.error(`${t('chat.copyFailed')}:`, err);
    });
  };

  const handleDeleteMessage = (id: string) => {
    updateMessages(messages.filter(msg => msg.id !== id));
  };

  const handleRegenerateMessage = useCallback(async (id: string) => {
    const messageToRegenerate = messages.find(msg => msg.id === id);
    if (messageToRegenerate && token) {
      const lastUserMessage = messages.filter(msg => msg.role === 'user').pop();
      if (lastUserMessage) {
        setLoading(true);
        
        // Create new bot message
        const newMessage: CustomChatMessage = {
          id: uuidv4(),
          content: '',
          role: 'bot',
          createAt: new Date().toISOString(),
          updateAt: new Date().toISOString(),
        };

        const updatedMessages = [...messages, newMessage];
        updateMessages(updatedMessages);
        currentBotMessageRef.current = newMessage;

        try {
          if (handleSendMessage) {
            const result = await handleSendMessage(lastUserMessage.content);
            
            // If handleSendMessage returns null, form validation failed, prevent regeneration
            if (result === null) {
              // Remove added messages and restore original state
              updateMessages(messages);
              setLoading(false);
              return;
            }
            
            const { url, payload } = result;
            await handleSSEStream(url, payload, newMessage);
          }
        } catch (error: any) {
          console.error(`${t('chat.regenerateFailed')}:`, error);

          updateMessages(prevMessages =>
            prevMessages.map(msgItem =>
              msgItem.id === newMessage.id
                ? { ...msgItem, content: t('chat.connectionError') }
                : msgItem
            )
          );
          setLoading(false);
        }
      }
    }
  }, [messages, token, handleSendMessage, handleSSEStream, updateMessages]);

  const renderContent = (msg: CustomChatMessage) => {
    const { content, knowledgeBase } = msg;
    // Parse reference links and make them clickable
    // If content is empty or just a default placeholder, show loading state
    const parsedContent = parseReferenceLinks(content || '');
    const parsedSuggestionContent = parseSuggestionLinks(parsedContent);
    
    return (
      <>
        <div
          dangerouslySetInnerHTML={{ __html: md.render(parsedSuggestionContent) }}
          className={styles.markdownBody}
          onClick={(e) => {
            handleReferenceClick(e);
            handleSuggestionClick(e);
          }}
        />
        {(Array.isArray(knowledgeBase) && knowledgeBase.length) ? <KnowledgeBase knowledgeList={knowledgeBase} /> : null}
      </>
    );
  };

  const renderSend = (props: ButtonProps & { ignoreLoading?: boolean; placeholder?: string } = {}) => {
    const { ignoreLoading, placeholder, ...btnProps } = props;

    return (
      <PermissionWrapper
        requiredPermissions={['Test']}>
        <Sender
          className={styles.sender}
          value={value}
          onChange={setValue}
          loading={loading}
          onSubmit={(msg: string) => {
            setValue('');
            handleSend(msg);
          }}
          placeholder={placeholder}
          onCancel={() => {
            stopSSEConnection();
          }}
          actions={((_: any, info: { components: { SendButton: React.ComponentType<ButtonProps>; LoadingButton: React.ComponentType<ButtonProps> } }) => {
            const { SendButton, LoadingButton } = info.components;
            if (!ignoreLoading && loading) {
              return (
                <Tooltip title={t('chat.clickCancel')}>
                  <LoadingButton />
                </Tooltip>
              );
            }
            let node: ReactNode = <SendButton {...btnProps} />;
            if (!ignoreLoading) {
              node = (
                <Tooltip title={value ? `${t('chat.send')}\u21B5` : t('chat.inputMessage')}>{node}</Tooltip>
              );
            }
            return node;
          }) as ActionRender}
        />
      </PermissionWrapper>
    );
  };

  const toggleAnnotationModal = (message: CustomChatMessage) => {
    if (message?.annotation) {
      setAnnotation(message.annotation);
    } else {
      const lastUserMessage = messages.slice(0, messages.indexOf(message)).reverse().find(msg => msg.role === 'user') as CustomChatMessage;
      setAnnotation({
        answer: message,
        question: lastUserMessage,
        selectedKnowledgeBase: '',
        tagId: 0,
      })
    }
    setAnnotationModalVisible(!annotationModalVisible);
  };

  const updateMessagesAnnotation = (id: string | undefined, newAnnotation?: Annotation) => {
    if (!id) return;
    updateMessages((prevMessages) =>
      prevMessages.map((msg) =>
        msg.id === id
          ? { ...msg, annotation: newAnnotation }
          : msg
      )
    );
    setAnnotationModalVisible(false);
  };

  const handleSaveAnnotation = (annotation?: Annotation) => {
    updateMessagesAnnotation(annotation?.answer?.id, annotation);
  };

  const handleRemoveAnnotation = (id: string | undefined) => {
    if (!id) return;
    updateMessagesAnnotation(id, undefined);
  };

  // Cleanup SSE connection on component unmount
  React.useEffect(() => {
    return () => {
      stopSSEConnection();
    };
  }, [stopSSEConnection]);

  const closeDrawer = useCallback(() => {
    setDrawerContent({
      visible: false,
      title: '',
      content: '',
      chunkType: undefined,
      graphData: undefined
    });
  }, []);

  const guideData = parseGuideItems(guide || '');

  return (
    <div className={`rounded-lg h-full ${isFullscreen ? styles.fullscreen : ''}`}>
      {mode === 'chat' &&
        <div className="flex justify-between items-center mb-3">
          <h2 className="text-base font-semibold">{t('chat.test')}</h2>
          <div>
            <button title="fullScreen" onClick={handleFullscreenToggle} aria-label="Toggle Fullscreen">
              {isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
            </button>
          </div>
        </div>
      }
      <div className={`flex flex-col rounded-lg p-4 h-full overflow-hidden ${styles.chatContainer}`} style={{ height: isFullscreen ? 'calc(100vh - 70px)' : (mode === 'chat' ? 'calc(100% - 40px)' : '100%') }}>
        {/* Guide content display area */}
        {guide && guideData.renderedHtml && (
          <div className="mb-4 flex items-start gap-3" onClick={handleGuideClick}>
            <div className="flex-shrink-0 mt-1">
              <Icon type="jiqiren3" className={styles.guideAvatar} />
            </div>
            <div
              dangerouslySetInnerHTML={{ __html: guideData.renderedHtml }}
              className={`${styles.markdownBody} flex-1 p-3 bg-[var(--color-bg)] rounded-lg`}
            />
          </div>
        )}
        
        <div 
          ref={chatContentRef}
          className="flex-1 chat-content-wrapper overflow-y-auto overflow-x-hidden pb-4"
        >
          <Flex gap="small" vertical>
            {messages.map((msg) => (
              <Bubble
                key={msg.id}
                className={styles.bubbleWrapper}
                placement={msg.role === 'user' ? 'end' : 'start'}
                loading={msg.content === '' && loading && currentBotMessageRef.current?.id === msg.id}
                content={renderContent(msg)}
                avatar={{ icon: <Icon type={msg.role === 'user' ? 'yonghu' : 'jiqiren3'} className={styles.avatar} /> }}
                footer={msg.content === '' && loading && currentBotMessageRef.current?.id === msg.id ? null : (
                  <MessageActions
                    message={msg}
                    onCopy={handleCopyMessage}
                    onRegenerate={handleRegenerateMessage}
                    onDelete={handleDeleteMessage}
                    onMark={toggleAnnotationModal}
                    showMarkOnly={showMarkOnly}
                  />
                )}
              />
            ))}
          </Flex>
        </div>
        
        {mode === 'chat' && (
          <>
            <div className="flex justify-end pb-2">
              <Popconfirm
                title={t('chat.clearConfirm')}
                okButtonProps={{ danger: true }}
                onConfirm={handleClearMessages}
                okText={t('chat.clear')}
                cancelText={t('common.cancel')}
              >
                <Button type="text" className="mr-2" icon={<Icon type="shanchu" className="text-2xl" />} />
              </Popconfirm>
            </div>
            <Flex vertical gap="middle">
              {renderSend({
                variant: 'text',
                placeholder: `${t('chat.inputPlaceholder')}`,
                color: 'primary',
                icon: <SendOutlined />,
                shape: 'default',
              })}
            </Flex>
          </>
        )}
      </div>
      {annotation && (
        <AnnotationModal
          visible={annotationModalVisible}
          showMarkOnly={showMarkOnly}
          annotation={annotation}
          onSave={handleSaveAnnotation}
          onRemove={handleRemoveAnnotation}
          onCancel={() => setAnnotationModalVisible(false)}
        />
      )}
      
      {/* Reference Details Drawer */}
      <Drawer
        width={drawerContent.chunkType === 'Graph' ? 800 : 480}
        visible={drawerContent.visible}
        title={drawerContent.title}
        onClose={closeDrawer}
      >
        {referenceModal.loading ? (
          <div className="flex justify-center items-center h-32">
            <Spin size="large" />
          </div>
        ) : (
          <>
            {drawerContent.chunkType === 'Graph' ? (
              <KnowledgeGraphView 
                data={drawerContent.graphData || { nodes: [], edges: [] }}
                height={500}
              />
            ) : (
              <div className="whitespace-pre-wrap leading-6">
                {drawerContent.content}
              </div>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
};

export default CustomChatSSE;