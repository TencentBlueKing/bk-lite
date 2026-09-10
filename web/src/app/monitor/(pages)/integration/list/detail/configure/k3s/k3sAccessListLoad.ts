export interface K3sAccessListLoadTicket {
  generation: number;
  objectId: number;
}

export interface K3sAccessListLoadDeps {
  objectId: number;
  getCloudRegionList: unknown;
  getInstanceList: unknown;
}

export interface K3sAccessListLoad {
  begin: (objectId: number) => K3sAccessListLoadTicket;
  shouldApply: (ticket: K3sAccessListLoadTicket) => boolean;
  invalidate: () => void;
}

/** 只按监控对象重载；API 函数身份变化不得触发新请求。 */
export function shouldReloadK3sAccessList(
  previous: K3sAccessListLoadDeps | null,
  next: K3sAccessListLoadDeps
): boolean {
  if (previous == null) {
    return true;
  }
  return previous.objectId !== next.objectId;
}

export function createK3sAccessListLoad(): K3sAccessListLoad {
  let generation = 0;

  return {
    begin(objectId: number): K3sAccessListLoadTicket {
      generation += 1;
      return { generation, objectId };
    },
    shouldApply(ticket: K3sAccessListLoadTicket): boolean {
      return ticket.generation === generation;
    },
    invalidate(): void {
      generation += 1;
    },
  };
}
