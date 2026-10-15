export interface MaterialBatchDeleteFeedback {
  level: "success" | "error";
  messageKey: string;
  defaultMessage: string;
  values?: Record<string, string | number>;
}

interface MaterialBatchDeleteOutcome {
  deleted_count: number;
  failed: { message: string } | null;
  not_attempted: number[];
}

export function materialBatchDeleteFeedback(
  result: MaterialBatchDeleteOutcome,
  nameOf: (id: number) => string,
): MaterialBatchDeleteFeedback | null {
  if (result.failed) {
    const pending = result.not_attempted ?? [];
    const failedMessage = result.failed.message;
    if (pending.length > 0) {
      return {
        level: "error",
        messageKey: "wiki.batchDeletePartial",
        defaultMessage:
          "已删除 {deleted} 条，未完成：{failed}。未继续处理 {notAttempted} 条：{notAttemptedNames}",
        values: {
          deleted: result.deleted_count,
          failed: failedMessage,
          notAttempted: pending.length,
          notAttemptedNames: pending.map((id) => nameOf(id)).join("、"),
        },
      };
    }
    return {
      level: "error",
      messageKey: "wiki.batchDeleteFailed",
      defaultMessage: "已删除 {deleted} 条，未完成：{failed}",
      values: {
        deleted: result.deleted_count,
        failed: failedMessage,
      },
    };
  }
  if (result.deleted_count > 0) {
    return {
      level: "success",
      messageKey: "wiki.deleteSuccess",
      defaultMessage: "删除成功",
    };
  }
  return null;
}
