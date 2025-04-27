export interface KnowledgeItem {
  score: number;
  content: string;
}

export interface KnowledgeBase {
  citing_num: number;
  knowledge_id: number;
  knowledge_base_id: number;
  knowledge_source_type: string;
  knowledge_title: string;
  result: KnowledgeItem[]
}

export interface Annotation {
  answer: CustomChatMessage;
  question: CustomChatMessage;
  selectedKnowledgeBase: string | number;
  tagId?: number | string;
}

export interface CustomChatMessage {
  id: string;
  role: 'user' | 'bot';
  content: string;
  createAt?: string;
  updateAt?: string;
  knowledgeBase?: KnowledgeBase | null;
  annotation?: Annotation | null;
}

export interface ResultItem {
  id: number;
  name: string;
  content: string;
  created_at?: string;
  created_by?: string;
  knowledge_source_type: string;
  rerank_score?: number;
  score: number;
}
