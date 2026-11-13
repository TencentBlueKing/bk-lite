"use client";
import React from "react";
import type { ChatContentState } from "./events";
import ApprovalCard from "./ApprovalCard";
import UserChoiceCard from "./UserChoiceCard";
import DiffReportCard from "./DiffReportCard";
import ConfigAnalysisReportCard from "./ConfigAnalysisReportCard";
import RepairCommandsCard from "./RepairCommandsCard";
import ReportDownloadCard from "./ReportDownloadCard";
import WikiCitations from "./WikiCitations";
import AgentStepProgress from "./AgentStepProgress";
import BrowserStepProgress from "./BrowserStepProgress";
import PlannedExecutionStatus from "./PlannedExecutionStatus";
import SkillView from "./SkillView";
import { ChatMarkdown } from "./Markdown";

export interface ContentCardsProps {
  state: ChatContentState;
  content?: string;
  readOnly?: boolean;
  onApproval?: (id: string, status: "approved" | "rejected") => void;
  onChoice?: (
    id: string,
    status: "pending" | "submitted" | "timeout",
    selected: string[],
  ) => void;
  onSendMessage?: (
    text: string,
    choice?: { choiceId: string; optionKey: string },
  ) => void;
}
export function ContentCards({
  state,
  content,
  readOnly = true,
  onApproval,
  onChoice,
  onSendMessage,
}: ContentCardsProps): React.JSX.Element {
  return (
    <>
      {!!state.agentStepProgress?.length && (
        <AgentStepProgress steps={state.agentStepProgress} />
      )}
      {state.browserStepsHistory && (
        <BrowserStepProgress history={state.browserStepsHistory} />
      )}
      {state.plannedExecutionStatus && (
        <PlannedExecutionStatus status={state.plannedExecutionStatus} />
      )}
      <SkillView items={state.skillViews} />
      {state.configDiffReports?.map((report) => (
        <DiffReportCard key={report.report_id} report={report} />
      ))}
      {state.configAnalysisReports?.map((report) =>
        report.severity_sections.length ? (
          <ConfigAnalysisReportCard key={report.report_id} report={report} />
        ) : (
          <ChatMarkdown
            key={report.report_id}
            content={report.fallback_markdown || report.markdown}
          />
        ),
      )}
      {state.repairCommands?.map((commands) => (
        <RepairCommandsCard key={commands.commands_id} commands={commands} />
      ))}
      {state.reportFileDownloads?.map((download) => (
        <ReportDownloadCard key={download.download_id} download={download} />
      ))}
      {state.approvalRequests?.map((request) => (
        <ApprovalCard
          key={request.tool_call_id}
          request={request}
          readOnly={readOnly}
          onDecision={onApproval || (() => undefined)}
        />
      ))}
      {state.userChoiceRequests?.map((request) => (
        <UserChoiceCard
          key={request.choice_id}
          request={request}
          token=""
          readOnly={readOnly}
          onSubmit={onChoice || (() => undefined)}
          onSendMessage={onSendMessage}
        />
      ))}
      {!!state.wikiCitations?.length && (
        <WikiCitations citations={state.wikiCitations} content={content} />
      )}
    </>
  );
}
