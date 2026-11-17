// @vitest-environment jsdom
import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { applyChatContentEvent, replayChatContent } from "@bk-lite/chat-content/events";
import { ChatMarkdown, renderChatMarkdown, ChatContentProvider, ApprovalCard, UserChoiceCard } from "@bk-lite/chat-content/ui";
import { loadWikiCitation } from '@bk-lite/chat-content/wikiCitation';
import { processHistoryMessageWithExtras } from "../historyMessageProcessor";
import { mapPlatformMessages } from "../../../../../../../webchat/packages/webchat-core/src/platform";

afterEach(cleanup);
it('refreshes citation images through the host without losing text on a signing failure', async () => {
  const locator = 'wiki/media/1/pages/0123456789abcdef.png';
  const markdown = `Reference\n![diagram](${locator})`;
  const displayUrl = `/api/proxy/opspilot/wiki_mgmt/media/?locator=${encodeURIComponent(locator)}&signature=test`;
  const calls: Array<[string, unknown]> = [];
  const citation = { id: 2, kind: 'page', title: 'Reference' };
  const result = await loadWikiCitation(citation, async <T,>(path: string, body?: unknown): Promise<T> => {
    calls.push([path, body]);
    return (body ? { urls: { [locator]: displayUrl } } : { body: markdown, knowledge_base: 1 }) as T;
  });
  expect(calls[1]).toEqual(['/opspilot/wiki_mgmt/knowledge_base/1/sign_media/', { locators: [locator] }]);
  expect(result).toContain(displayUrl);
  expect(await loadWikiCitation(citation, async <T,>(_path: string, body?: unknown): Promise<T> => {
    if (body) throw new Error('unavailable');
    return { body: markdown, knowledge_base: 1 } as T;
  })).toEqual(markdown);
});
const events = [
  { type: "TEXT_MESSAGE_CONTENT", delta: "检查结果 [1]" },
  {
    type: "CUSTOM",
    name: "wiki_citations",
    value: { citations: [{ n: 1, id: 7, kind: "page", title: "检查规范" }] },
  },
  {
    type: "CUSTOM",
    name: "skill_view",
    value: { items: [{ id: "k8s", name: "Kubernetes Specialist" }] },
  },
  {
    type: "CUSTOM",
    name: "repair_commands",
    value: {
      commands_id: "repair",
      commands_markdown: "```sh\nkubectl get pods\n```",
    },
  },
  {
    type: "CUSTOM",
    name: "repair_diff_report",
    value: {
      report_id: "diff",
      title: "配置差异",
      cluster_name: "demo",
      items: [],
    },
  },
  {
    type: "CUSTOM",
    name: "user_choice_request",
    value: {
      choice_id: "choice",
      title: "选择目标",
      multiple: true,
      min_select: 2,
      options: ["A", "B"],
    },
  },
  {
    type: "CUSTOM",
    name: "user_choice_result",
    value: { choice_id: "choice", selected: ["A", "B"], source: "user" },
  },
  {
    type: "CUSTOM",
    name: "planned_execution_step",
    value: { phase: "start", step_index: 1, total_steps: 1, objective: "扫描" },
  },
  { type: "TOOL_CALL_START", toolCallId: "tool", toolCallName: "scan" },
  { type: "RUN_FINISHED" },
];

describe("one content model across live and both history adapters", () => {
  it("retains reports, citations and selected values in both histories", () => {
    const live = events.reduce(
      (state, event) =>
        event.type === "CUSTOM"
          ? applyChatContentEvent(state, event.name!, event.value, 0)
          : state,
      {},
    );
    const history = replayChatContent(events);
    expect(live).toEqual(history);
    const debug = processHistoryMessageWithExtras(events, "bot");
    const platform = mapPlatformMessages([
      { id: "m1", role: "assistant", content: events },
    ])[0];
    for (const [key, value] of Object.entries(history)) {
      expect(debug[key], `debug ${key}`).toEqual(value);
      expect(platform.metadata?.[key], `platform ${key}`).toEqual(value);
    }
    expect(platform.metadata?.plannedSteps).toMatchObject([
      { objective: "扫描", status: "done", toolCallIds: ["tool"] },
    ]);
    expect(debug.plannedExecutionSteps).toMatchObject([
      { objective: "扫描", status: "done", toolCallIds: ["tool"] },
    ]);
  });
  it("retains a card-only answer and does not duplicate a replayed report", () => {
    const event = events[3];
    const rows = mapPlatformMessages([
      { role: "assistant", content: [event, event] },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].metadata?.repairCommands).toHaveLength(1);
  });
});

it("renders semantic tables and highlighted code, sanitizes unsafe content", () => {
  const { container } = render(
    <ChatMarkdown
      content={
        '| 严重级别 | 问题项 |\n| --- | --- |\n| 高 | 缺少探针 |\n\n```js\nconst count = 90;\n```\n\n<img src="x" onerror="alert(1)"><script>alert(1)</script>'
      }
    />,
  );
  expect(container.querySelector("thead th")?.textContent).toBe("严重级别");
  expect(container.querySelector("pre pre")).toBeNull();
  expect(container.querySelector(".hljs-keyword")?.textContent).toBe("const");
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("[onerror]")).toBeNull();
  expect(
    renderChatMarkdown('<img src="x" onerror="alert(1)">', true),
  ).not.toContain("onerror");
  expect(renderChatMarkdown("[bad](javascript:alert(1))")).not.toContain(
    'href="javascript:',
  );
});

it("shows approval arguments and submits the reason through the host", async () => {
  const submissions: Record<string, unknown>[] = [];
  const request = replayChatContent([
    {
      type: "CUSTOM",
      name: "approval_request",
      value: {
        execution_id: "e",
        node_id: "n",
        tool_call_id: "t",
        tool_name: "restart",
        tool_args: { namespace: "prod" },
      },
    },
  ]).approvalRequests![0];
  const { getByText, getByPlaceholderText } = render(
    <ChatContentProvider
      value={{
        submitApproval: async (body) => {
          submissions.push(body);
        },
      }}
    >
      <ApprovalCard request={request} onDecision={() => undefined} />
    </ChatContentProvider>,
  );
  expect(getByText(/"namespace": "prod"/)).toBeTruthy();
  fireEvent.change(getByPlaceholderText(/原因|理由/), {
    target: { value: "已确认窗口" },
  });
  fireEvent.click(getByText("批准"));
  await waitFor(() => expect(submissions).toHaveLength(1));
  expect(submissions[0]).toMatchObject({
    tool_call_id: "t",
    decision: "approve",
    reason: "已确认窗口",
  });
});

it("does not permit submitting an expired choice", () => {
  const request = replayChatContent([
    {
      type: "CUSTOM",
      name: "user_choice_request",
      value: {
        choice_id: "expired",
        title: "选择",
        timeout_seconds: 1,
        options: ["A", "B"],
      },
    },
  ]).userChoiceRequests![0];
  const { queryByRole } = render(
    <UserChoiceCard
      request={request}
      token=""
      onSubmit={() => {
        throw new Error("expired submit");
      }}
    />,
  );
  expect(queryByRole("button", { name: "A" })).toBeNull();
});
