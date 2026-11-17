import type {
  AgentStepProgressData,
  BrowserStepsHistory,
  PlannedExecutionStatusValue,
  ApprovalRequest,
  UserChoiceRequest,
  ConfigDiffReport,
  ConfigAnalysisReport,
  RepairCommands,
  ReportFileDownload,
  SkillViewItem,
  WikiCitation,
} from "./types";
import { normalizeUserChoiceOptions } from "./userChoiceOptions";

export interface ChatContentState {
  agentStepProgress?: AgentStepProgressData[];
  browserStepsHistory?: BrowserStepsHistory;
  plannedExecutionStatus?: PlannedExecutionStatusValue;
  approvalRequests?: ApprovalRequest[];
  userChoiceRequests?: UserChoiceRequest[];
  configDiffReports?: ConfigDiffReport[];
  configAnalysisReports?: ConfigAnalysisReport[];
  reportFileDownloads?: ReportFileDownload[];
  repairCommands?: RepairCommands[];
  skillViews?: SkillViewItem[];
  wikiCitations?: WikiCitation[];
}
const names = new Set([
  "agent_step_progress",
  "sub_agent_progress",
  "browser_step_progress",
  "planned_execution_status",
  "approval_request",
  "user_choice_request",
  "user_choice_result",
  "repair_diff_report",
  "config_diff_report",
  "config_analysis_report",
  "report_file_download",
  "repair_commands",
  "skill_view",
  "wiki_citations",
]);
export const isChatContentEvent = (name: string) => names.has(name);
const record = (value: unknown): Record<string, any> | null => {
  if (typeof value === "string") {
    try {
      return record(JSON.parse(value));
    } catch {
      return null;
    }
  }
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : null;
};
function upsert<T>(items: T[] | undefined, next: T, key: keyof T): T[] {
  const result = [...(items || [])];
  const index = result.findIndex((item) => item[key] === next[key]);
  if (index < 0) result.push(next);
  else result[index] = next;
  return result;
}
/** One transition for both live events and stored history. Hosts own transport and rendering. */
export function applyChatContentEvent(
  state: ChatContentState,
  name: string,
  raw: unknown,
  receivedAt: number,
): ChatContentState {
  const value = record(
    name === "wiki_citations" && Array.isArray(raw) ? { citations: raw } : raw,
  );
  if (!value) return state;
  const timed = {
    ...value,
    received_at:
      typeof value.received_at === "number" ? value.received_at : receivedAt,
  };
  switch (name) {
    case "agent_step_progress":
    case "sub_agent_progress": {
      if (typeof value.status !== "string") return state;
      const step = { step: 0, max_steps: 0, ...value } as AgentStepProgressData;
      const steps = [...(state.agentStepProgress || [])];
      const index = steps.findIndex(
        (item) =>
          item.agent_name === step.agent_name &&
          (name === "sub_agent_progress" || item.step === step.step),
      );
      if (index < 0) steps.push(step);
      else steps[index] = step;
      return { ...state, agentStepProgress: steps };
    }
    case "browser_step_progress": {
      if (typeof value.step_number !== "number") return state;
      const steps = upsert(
        state.browserStepsHistory?.steps,
        value as unknown as BrowserStepsHistory["steps"][number],
        "step_number",
      );
      return { ...state, browserStepsHistory: { steps, isRunning: true } };
    }
    case "planned_execution_status":
      return {
        ...state,
        plannedExecutionStatus: value as PlannedExecutionStatusValue,
      };
    case "approval_request": {
      if (!value.tool_call_id) return state;
      const previous = state.approvalRequests?.find(
        (item) => item.tool_call_id === value.tool_call_id,
      );
      const request = {
        tool_args: {},
        timeout_seconds: 0,
        ...timed,
        status: previous?.status ?? "pending",
        received_at: previous?.received_at ?? timed.received_at,
      } as ApprovalRequest;
      return {
        ...state,
        approvalRequests: upsert(
          state.approvalRequests,
          request,
          "tool_call_id",
        ),
      };
    }
    case "user_choice_request": {
      if (!value.choice_id) return state;
      const previous = state.userChoiceRequests?.find(
        (item) => item.choice_id === value.choice_id,
      );
      const request = {
        multiple: false,
        min_select: 1,
        max_select: 0,
        timeout_seconds: 0,
        default_keys: [],
        display_hint: "auto",
        ...timed,
        options: normalizeUserChoiceOptions(value.options),
        status: previous?.status ?? "pending",
        selected: previous?.selected,
        received_at: previous?.received_at ?? timed.received_at,
      } as unknown as UserChoiceRequest;
      return {
        ...state,
        userChoiceRequests: upsert(
          state.userChoiceRequests,
          request,
          "choice_id",
        ),
      };
    }
    case "user_choice_result":
      return {
        ...state,
        userChoiceRequests: state.userChoiceRequests?.map((item) =>
          item.choice_id === value.choice_id
            ? {
              ...item,
              status: value.source === "user" ? "submitted" : "timeout",
              selected: Array.isArray(value.selected) ? value.selected : [],
            }
            : item,
        ),
      };
    case "repair_diff_report":
    case "config_diff_report":
      if (!value.report_id || !Array.isArray(value.items)) return state;
      return {
        ...state,
        configDiffReports: upsert(
          state.configDiffReports,
          timed as ConfigDiffReport,
          "report_id",
        ),
      };
    case "config_analysis_report": {
      if (!value.report_id) return state;
      const report = {
        ...timed,
        summary: value.summary || {},
        severity_sections: (Array.isArray(value.severity_sections)
          ? value.severity_sections
          : []
        )
          .filter(record)
          .map((section: any) => ({
            ...section,
            issues: Array.isArray(section.issues)
              ? section.issues
              : Array.isArray(section.items)
                ? section.items
                : [],
          })),
        recommendations: (Array.isArray(value.recommendations)
          ? value.recommendations
          : []
        ).filter(
          (item: any) =>
            item &&
            ["P0", "P1", "P2", "P3"].includes(item.priority) &&
            typeof item.action === "string" &&
            item.action.trim() &&
            typeof item.target === "string" &&
            item.target.trim() &&
            typeof item.benefit === "string" &&
            item.benefit.trim(),
        ),
        markdown: value.markdown || "",
        fallback_markdown: value.fallback_markdown || value.markdown || "",
      } as ConfigAnalysisReport;
      return {
        ...state,
        configAnalysisReports: upsert(
          state.configAnalysisReports,
          report,
          "report_id",
        ),
      };
    }
    case "report_file_download":
      if (!value.download_id || !value.filename) return state;
      return {
        ...state,
        reportFileDownloads: upsert(
          state.reportFileDownloads,
          timed as ReportFileDownload,
          "download_id",
        ),
      };
    case "repair_commands":
      if (typeof value.commands_markdown !== "string") return state;
      return {
        ...state,
        repairCommands: upsert(
          state.repairCommands,
          {
            ...timed,
            commands_id: value.commands_id || "repair-commands",
          } as RepairCommands,
          "commands_id",
        ),
      };
    case "skill_view":
      return {
        ...state,
        skillViews: (Array.isArray(value.items) ? value.items : []).filter(
          (item) => item && typeof item.name === "string",
        ),
      };
    case "wiki_citations": {
      let citations = state.wikiCitations || [];
      for (const item of Array.isArray(value.citations)
        ? value.citations
        : []) {
        if (item && item.id && typeof item.title === "string") {
          citations = [
            ...citations.filter(
              (c) => !(c.id === item.id && c.kind === item.kind),
            ),
            item,
          ];
        }
      }
      return { ...state, wikiCitations: citations };
    }
    default:
      return state;
  }
}
export function replayChatContent(
  events: Array<Record<string, unknown>>,
  receivedAt = 0,
): ChatContentState {
  const state = events.reduce(
    (state, event) =>
      event.type === "CUSTOM"
        ? applyChatContentEvent(
          state,
          String(event.name || ""),
          event.value,
          receivedAt,
        )
        : state,
    {} as ChatContentState,
  );
  return {
    ...state,
    ...(state.browserStepsHistory
      ? {
        browserStepsHistory: {
          ...state.browserStepsHistory,
          isRunning: false,
        },
      }
      : {}),
    ...(state.plannedExecutionStatus
      ? {
        plannedExecutionStatus: {
          ...state.plannedExecutionStatus,
          phase: "idle",
        },
      }
      : {}),
  };
}
