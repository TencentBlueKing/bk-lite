import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Spin } from 'antd';
import throttle from 'lodash/throttle';
import styles from './index.module.scss';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import useApiClient from '@/utils/request';
import CustomChat from '@/app/opspilot/components/custom-chat';
import { fetchLogDetails, createConversation } from '@/app/opspilot/utils/logUtils';

interface ChatComponentProps {
  initialChats: CustomChatMessage[];
  conversationId: number[];
  count: number;
}

const ProChatComponentWrapper: React.FC<ChatComponentProps> = ({ initialChats, conversationId, count }) => {
  const { get, post } = useApiClient();
  const [messages, setMessages] = useState<CustomChatMessage[]>(initialChats);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const proChatContainerRef = useRef<HTMLDivElement | null>(null);

  const fetchMoreData = useCallback(async () => {
    if (loading || !hasMore) return;
    setLoading(true);

    try {
      const nextPage = page + 1;
      const data = await fetchLogDetails(post, conversationId, nextPage);
      
      if (data.length === 0) {
        setHasMore(false);
      } else {
        const newMessages = await createConversation(data, get);
        setMessages((prevMessages) => {
          const updatedMessages = [...prevMessages, ...newMessages];
          if (updatedMessages.length >= count) {
            setHasMore(false);
          }
          return updatedMessages;
        });
        setPage(nextPage);
      }
    } catch (error) {
      console.error('Error fetching more data:', error);
    } finally {
      setLoading(false);
    }
  }, [loading, hasMore, page, conversationId, count, get, post]);

  const handleScroll = useCallback(throttle(() => {
    const scrollElement = proChatContainerRef.current?.querySelector('.chat-content-wrapper') as HTMLDivElement;
    if (!scrollElement || loading || !hasMore) return;

    const { scrollTop, scrollHeight, clientHeight } = scrollElement;
    if (scrollTop + clientHeight >= scrollHeight - 300) {
      fetchMoreData();
    }
  }, 200), [loading, hasMore]);

  useEffect(() => {
    setMessages(initialChats);
    setPage(1);
    setHasMore(initialChats.length < count);
    setLoading(false);
  }, [initialChats, count]);

  useEffect(() => {
    const proChatContainer = proChatContainerRef.current;
    const scrollElement = proChatContainer?.querySelector('.chat-content-wrapper') as HTMLDivElement;

    if (scrollElement) {
      scrollElement.addEventListener('scroll', handleScroll);
    }

    return () => {
      if (scrollElement) {
        scrollElement.removeEventListener('scroll', handleScroll);
      }
    };
  }, [handleScroll]);

  return (
    <div className={`rounded-lg h-full ${styles.proChatDetail}`} ref={proChatContainerRef}>
      <CustomChat 
        initialMessages={messages} 
        showMarkOnly={true} 
        mode='preview' 
      />
      {loading && <div className='flex justify-center items-center'><Spin /></div>}
    </div>
  );
};

export default ProChatComponentWrapper;
