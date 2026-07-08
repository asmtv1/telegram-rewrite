import type { PostItem } from "./api";

export type DraftTextByPostId = Record<number, string>;

export function nextDraftsForTextChange(
  current: DraftTextByPostId,
  post: PostItem,
  text: string
): DraftTextByPostId {
  if ((post.rewritten_text ?? "") === text) {
    const { [post.id]: _removed, ...rest } = current;
    return rest;
  }
  return { ...current, [post.id]: text };
}

export function isPublishedDraft(
  post: PostItem | null,
  targetChannel: string,
  text: string,
  mediaUrls: string[]
): boolean {
  return (
    Boolean(post && post.publish_status === "published") &&
    sameChannel(post?.target_channel, targetChannel) &&
    (post?.rewritten_text ?? "").trim() === text.trim() &&
    sameStringList(post?.published_media_urls ?? [], mediaUrls)
  );
}

function canonicalChannel(value: string | null | undefined): string {
  const raw = (value ?? "").trim();
  const match = raw.match(/^(?:https?:\/\/)?t\.me\/([A-Za-z0-9_]+)(?:\/\d+)?\/?$/i);
  return (match ? match[1] : raw.replace(/^@/, "")).toLowerCase();
}

function sameChannel(left: string | null | undefined, right: string | null | undefined): boolean {
  return canonicalChannel(left) === canonicalChannel(right);
}

function sameStringList(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}
