import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';
import { processHistoryMessageWithExtras } from '@/app/opspilot/components/custom-chat-sse/historyMessageProcessor';

export const fetchLogDetails = async (post: any, conversationId: number[], page = 1, pageSize = 20) => {
  return await post('/opspilot/bot_mgmt/bot/get_workflow_log_detail/', {
    ids: conversationId,
    page: page,
    page_size: pageSize,
  });
};

export const createConversation = async (data: any[], get: any): Promise<CustomChatMessage[]> => {
  return await Promise.all(data.map(async (item, index) => {
    const correspondingUserMessage = data.slice(0, index).reverse().find(({ role }) => role === 'user') as CustomChatMessage | undefined;
    const rawRole = item.role ?? item.conversation_role ?? item.conversationRole ?? item.role_name;
    const normalizedRole = rawRole === 'assistant' ? 'bot' : rawRole;
    const rawContent = item.content ?? item.conversation_content ?? item.conversationContent ?? '';
    const entryType = item.entry_type ?? item.entryType ?? item.conversation_entry_type;
    const shouldProcess = normalizedRole === 'bot' && (entryType === 'AG-UI' || (typeof rawContent === 'string' && rawContent.trim().startsWith('[')));
    const processed = shouldProcess
      ? processHistoryMessageWithExtras(rawContent, 'bot')
      : { content: rawContent, browserStepProgress: null, browserStepsHistory: null };
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
      role: normalizedRole,
      content: processed.content,
      createAt: item.conversation_time ? new Date(item.conversation_time).toISOString() : undefined,
      updateAt: item.conversation_time ? new Date(item.conversation_time).toISOString() : undefined,
      annotation: annotation,
      knowledgeBase: item.citing_knowledge,
      browserStepProgress: processed.browserStepProgress ?? null,
      browserStepsHistory: processed.browserStepsHistory ?? null,
    } as CustomChatMessage;
  }));
};
