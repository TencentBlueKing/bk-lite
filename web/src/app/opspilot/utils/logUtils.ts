import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';

export const fetchLogDetails = async (post: any, conversationId: number[], page = 1, pageSize = 20) => {
  return await post('/opspilot/bot_mgmt/history/get_log_detail/', {
    ids: conversationId,
    page: page,
    page_size: pageSize,
  });
};

export const createConversation = async (data: any[], get: any): Promise<CustomChatMessage[]> => {
  return await Promise.all(data.map(async (item, index) => {
    const correspondingUserMessage = data.slice(0, index).reverse().find(({ role }) => role === 'user') as CustomChatMessage | undefined;
    let tagDetail;
    if (item.tag_id) {
      const params = { tag_id: item.tag_id };
      tagDetail = await get('/opspilot/bot_mgmt/history/get_tag_detail/', { params });
    }

    const annotation: Annotation | null = item.has_tag ? {
      answer: {
        id: item.id,
        role: 'bot',
        content: tagDetail?.content || item.content,
      },
      question: correspondingUserMessage ? {
        id: correspondingUserMessage.id,
        role: 'user',
        content: tagDetail?.question || correspondingUserMessage.content,
      } : { id: '', role: 'user', content: '' },
      selectedKnowledgeBase: tagDetail?.knowledge_base_id,
      tagId: item.tag_id,
    } : null;

    return {
      id: item.id,
      role: item.role,
      content: item.content,
      annotation: annotation,
      knowledgeBase: item.citing_knowledge,
    } as CustomChatMessage;
  }));
};
