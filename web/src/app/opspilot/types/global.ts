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

export interface BrowserStepAction {
  navigate?: { url: string; new_tab?: boolean };
  wait?: { seconds: number };
  input?: { index: number; text: string; clear?: boolean };
  click?: { index: number };
  scroll?: { direction?: 'up' | 'down'; amount?: number };
  screenshot?: boolean;
  [key: string]: unknown;
}

export interface BrowserStepProgressData {
  step_number: number;
  max_steps: number;
  url: string;
  title: string;
  thinking: string;
  evaluation: string;
  memory: string;
  next_goal: string;
  actions: BrowserStepAction[];
  has_screenshot: boolean;
  screenshot?: string;
}

export interface BrowserStepsHistory {
  steps: BrowserStepProgressData[];
  isRunning: boolean;
}

export interface CustomChatMessage {
  id: string;
  role: 'user' | 'bot';
  content: string;
  createAt?: string;
  updateAt?: string;
  knowledgeBase?: KnowledgeBase | null;
  annotation?: Annotation | null;
  images?: Array<{
    id: string;
    url: string;
    name?: string;
    status?: 'uploading' | 'done' | 'error';
  }>;
  browserStepProgress?: BrowserStepProgressData | null;
  browserStepsHistory?: BrowserStepsHistory | null;
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
