import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';
import { processHistoryMessageWithExtras } from '@/app/opspilot/components/custom-chat-sse/historyMessageProcessor';

export const fetchLogDetails = async (post: any, conversationId: number[], page = 1, pageSize = 20) => {
  return await post('/opspilot/bot_mgmt/bot/get_workflow_log_detail/', {
    ids: conversationId,
    page: page,
    page_size: pageSize,
  });
};

export const createConversation = async (data: any, get: any): Promise<CustomChatMessage[]> => {
  const items: any[] = Array.isArray(data)
    ? data
    : Array.isArray(data?.data)
      ? data.data
      : [];

  return await Promise.all(items.map(async (item, index) => {
    const correspondingUserMessage = data.slice(0, index).reverse().find(({ role }) => role === 'user') as CustomChatMessage | undefined;
    const rawRole = item.role ?? item.conversation_role ?? item.conversationRole ?? item.role_name;
    const normalizedRole = rawRole === 'assistant' ? 'bot' : rawRole;
    const rawContent = item.content ?? item.conversation_content ?? item.conversationContent ?? '';
    const entryType = item.entry_type ?? item.entryType ?? item.conversation_entry_type;

    const normalizePythonJson = (raw: string) => {
      const replacedLiterals = raw
        .replace(/\bNone\b/g, 'null')
        .replace(/\bTrue\b/g, 'true')
        .replace(/\bFalse\b/g, 'false');
      return replacedLiterals.replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, value) => {
        const unescaped = value.replace(/\\'/g, "'");
        const escaped = unescaped.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        return `"${escaped}"`;
      });
    };

    const parseJsonValue = (raw: string): any => {
      try {
        return JSON.parse(raw);
      } catch {
        // ignore
      }
      try {
        return JSON.parse(normalizePythonJson(raw));
      } catch {
        return null;
      }
    };

    const extractOpenAIContent = (value: any) => {
      if (!value) return '';
      if (Array.isArray(value)) {
        return value.map(item => extractOpenAIContent(item)).join('');
      }
      if (typeof value === 'object') {
        const choices = value.choices;
        if (Array.isArray(choices)) {
          return choices
            .map(choice => choice?.delta?.content || '')
            .join('');
        }
      }
      return '';
    };

    const shouldProcessAGUI = normalizedRole === 'bot' && (entryType === 'AG-UI' || (typeof rawContent === 'string' && rawContent.trim().startsWith('[')));
    const shouldProcessOpenAI = normalizedRole === 'bot' && entryType === 'OpenAI';

    let processed: { content: any; browserStepProgress: any; browserStepsHistory: any } = {
      content: rawContent,
      browserStepProgress: null,
      browserStepsHistory: null
    };
    if (shouldProcessAGUI) {
      const parsed = processHistoryMessageWithExtras(rawContent, 'bot');
      processed = {
        content: parsed.content,
        browserStepProgress: parsed.browserStepProgress ?? null,
        browserStepsHistory: parsed.browserStepsHistory ?? null
      };
    } else if (shouldProcessOpenAI) {
      const parsed = typeof rawContent === 'string' ? parseJsonValue(rawContent) : rawContent;
      const extracted = extractOpenAIContent(parsed);
      processed = { content: extracted || (typeof rawContent === 'string' ? rawContent : String(rawContent ?? '')), browserStepProgress: null, browserStepsHistory: null };
    }
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
