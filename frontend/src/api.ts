export type CurrentUser = {
  user_id: string;
};

export type TelegramStatus = {
  connected: boolean;
  phone: string | null;
  needs_credentials: boolean;
};

export type PostItem = {
  id: number;
  source_channel: string;
  source_channel_id: string | null;
  target_channel: string | null;
  telegram_message_id: number;
  original_text: string;
  rewritten_text: string | null;
  publish_status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  published_message_id: number | null;
  published_url: string | null;
  media_urls: string[];
  published_media_urls: string[] | null;
};

export type PostsPage = {
  items: PostItem[];
  next_offset_id: number | null;
  has_more: boolean;
  message: string | null;
};

export type PostsHistory = {
  items: PostItem[];
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers ?? {})
    },
    ...options
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // Keep statusText.
    }
    throw new Error(String(detail));
  }
  return (await response.json()) as T;
}

export const api = {
  me: () => request<CurrentUser>("/api/auth/me"),
  login: (username: string, password: string) =>
    request<{ ok: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  telegramStatus: () => request<TelegramStatus>("/api/telegram/status"),
  telegramSendCode: (phone: string) =>
    request<{ ok: boolean }>("/api/telegram/send-code", {
      method: "POST",
      body: JSON.stringify({ phone })
    }),
  telegramSignIn: (code: string) =>
    request<{ ok?: boolean; password_required: boolean }>("/api/telegram/sign-in", {
      method: "POST",
      body: JSON.stringify({ code })
    }),
  telegramPassword: (password: string) =>
    request<{ ok: boolean }>("/api/telegram/password", {
      method: "POST",
      body: JSON.stringify({ password })
    }),
  telegramLogout: () => request<{ ok: boolean }>("/api/telegram/logout", { method: "POST" }),
  posts: (source_channel: string, target_channel?: string, offset_id?: number | null, signal?: AbortSignal) => {
    const params = new URLSearchParams({ source_channel });
    if (target_channel?.trim()) params.set("target_channel", target_channel);
    if (offset_id) params.set("offset_id", String(offset_id));
    return request<PostsPage>(`/api/posts?${params.toString()}`, { signal });
  },
  history: () => request<PostsHistory>("/api/posts/history"),
  rewrite: (postId: number, prompt: string) =>
    request<PostItem>(`/api/posts/${postId}/rewrite`, {
      method: "POST",
      body: JSON.stringify({ prompt })
    }),
  uploadMedia: (postId: number, files: File[]) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    return request<{ media_urls: string[] }>(`/api/posts/${postId}/media`, {
      method: "POST",
      body: formData
    });
  },
  publish: (postId: number, target_channel: string, text: string, media_urls?: string[]) =>
    request<PostItem>(`/api/posts/${postId}/publish`, {
      method: "POST",
      body: JSON.stringify({ target_channel, text, media_urls })
    })
};
