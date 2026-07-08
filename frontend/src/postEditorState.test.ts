import { describe, expect, it } from "vitest";
import type { PostItem } from "./api";
import { nextDraftsForTextChange, isPublishedDraft } from "./postEditorState";

const publishedPost: PostItem = {
  id: 2,
  source_channel: "@source",
  source_channel_id: null,
  target_channel: "@asmtv2",
  telegram_message_id: 10,
  original_text: "original",
  rewritten_text: "published text",
  publish_status: "published",
  error_message: null,
  created_at: "2026-07-08T18:00:00Z",
  updated_at: "2026-07-08T18:01:00Z",
  published_at: "2026-07-08T18:02:00Z",
  published_message_id: 777,
  published_url: "https://t.me/asmtv2/777",
  media_urls: [],
  published_media_urls: []
};

describe("post editor state", () => {
  it("treats a changed result as an unpublished draft", () => {
    expect(isPublishedDraft(publishedPost, "@asmtv2", "published text", [])).toBe(true);
    expect(isPublishedDraft(publishedPost, "@asmtv2", "changed text", [])).toBe(false);
  });

  it("keeps a local draft when result text differs from saved post text", () => {
    expect(nextDraftsForTextChange({}, publishedPost, "changed text")).toEqual({
      [publishedPost.id]: "changed text"
    });
  });

  it("drops the local draft when result text returns to saved post text", () => {
    expect(nextDraftsForTextChange({ [publishedPost.id]: "changed text" }, publishedPost, "published text")).toEqual({});
  });
});
