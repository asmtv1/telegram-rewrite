export type ActiveRequest = {
  key: string;
  controller: AbortController;
};

export type ActiveRequestRef = {
  current: ActiveRequest | null;
};

type RequestStart =
  | { status: "started"; controller: AbortController }
  | { status: "duplicate" };

export function beginExclusiveRequest(ref: ActiveRequestRef, key: string): RequestStart {
  if (ref.current?.key === key) {
    return { status: "duplicate" };
  }
  ref.current?.controller.abort();

  const controller = new AbortController();
  ref.current = { key, controller };
  return { status: "started", controller };
}

export function isCurrentRequest(ref: ActiveRequestRef, controller: AbortController): boolean {
  return ref.current?.controller === controller;
}

export function finishExclusiveRequest(ref: ActiveRequestRef, controller: AbortController): void {
  if (isCurrentRequest(ref, controller)) {
    ref.current = null;
  }
}
