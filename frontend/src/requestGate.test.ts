import { describe, expect, it } from "vitest";
import {
  beginExclusiveRequest,
  finishExclusiveRequest,
  isCurrentRequest,
  type ActiveRequestRef
} from "./requestGate";

describe("request gate", () => {
  it("ignores duplicate requests with the same key", () => {
    const ref: ActiveRequestRef = { current: null };
    const first = beginExclusiveRequest(ref, "posts:@source:first");
    const second = beginExclusiveRequest(ref, "posts:@source:first");

    expect(first.status).toBe("started");
    expect(second.status).toBe("duplicate");
    expect(ref.current?.key).toBe("posts:@source:first");
  });

  it("aborts the previous request when a new key starts", () => {
    const ref: ActiveRequestRef = { current: null };
    const first = beginExclusiveRequest(ref, "posts:@old:first");
    const firstController = first.status === "started" ? first.controller : null;

    const second = beginExclusiveRequest(ref, "posts:@new:first");
    const secondController = second.status === "started" ? second.controller : null;

    expect(firstController?.signal.aborted).toBe(true);
    expect(second.status).toBe("started");
    expect(secondController?.signal.aborted).toBe(false);
    expect(isCurrentRequest(ref, firstController!)).toBe(false);

    finishExclusiveRequest(ref, firstController!);
    expect(ref.current?.key).toBe("posts:@new:first");

    finishExclusiveRequest(ref, secondController!);
    expect(ref.current).toBeNull();
  });
});
