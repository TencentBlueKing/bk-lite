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
      const data = await fetchLogDetails(post, conversationId, page + 1);
      if (data.length === 0 || count <= messages.length) {
        setHasMore(false);
      } else {
        const newMessages = await createConversation(data, get);
        setMessages((prevMessages) => [...prevMessages, ...newMessages]);
        setPage((prevPage) => prevPage + 1);
      }
    } catch (error) {
      console.error('Error fetching more data:', error);
    } finally {
      setLoading(false);
    }
  }, [loading, hasMore, page, conversationId, post, count, messages]);

  const handleScroll = useCallback(throttle(() => {
    const scrollElement = proChatContainerRef.current?.querySelector('.chat-content-wrapper') as HTMLDivElement;
    if (!scrollElement || loading || !hasMore) return;

    const { scrollTop, scrollHeight, clientHeight } = scrollElement;
    if (scrollTop + clientHeight >= scrollHeight - 300) {
      fetchMoreData();
    }
  }, 200), [fetchMoreData, hasMore, loading]);

  useEffect(() => {
    if (page === 1) {
      fetchMoreData();
    }
  }, [fetchMoreData, page]);

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
      <CustomChat initialMessages={messages} showMarkOnly={true} mode='preview' />
      {loading && <div className='flex justify-center items-center'><Spin /></div>}
    </div>
  );
};

export default ProChatComponentWrapper;
