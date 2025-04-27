export interface Skill {
  id: number;
  name: string;
  introduction: string;
  created_by: string;
  team: string[];
  team_name: string;
}

export interface ModifySkillModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: Skill) => void;
  initialValues?: Skill | null;
}

export interface RagScoreThresholdItem {
  knowledge_base: number;
  score: number;
}

export interface KnowledgeBase {
  id: number;
  name: string;
  introduction?: string;
}

export interface SelectorOption {
  id: number;
  name: string;
  icon?: string;
}

export interface KnowledgeBaseRagSource {
  id: number,
  name: string,
  introduction: string,
  score?: number
}
