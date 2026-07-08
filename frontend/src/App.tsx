import { FormEvent, KeyboardEvent, memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Virtuoso } from "react-virtuoso";
import {
  Check,
  History,
  ImagePlus,
  LogOut,
  Plus,
  RefreshCcw,
  Send,
  Sparkles,
  Unplug,
  X
} from "lucide-react";
import { api, PostItem, TelegramStatus } from "./api";
import {
  beginExclusiveRequest,
  finishExclusiveRequest,
  isCurrentRequest,
  type ActiveRequestRef
} from "./requestGate";

type Notice = {
  kind: "idle" | "loading" | "success" | "error";
  text: string;
};

const idle: Notice = { kind: "idle", text: "" };

function App() {
  const [user, setUser] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    api
      .me()
      .then((me) => setUser(me.user_id))
      .catch(() => setUser(null))
      .finally(() => setBooting(false));
  }, []);

  if (booting) return <main className="screen center">Загрузка...</main>;

  return (
    <main className="screen">
      {user ? <Workspace user={user} onLogout={() => setUser(null)} /> : <Login onLogin={setUser} />}
    </main>
  );
}

function Login({ onLogin }: { onLogin: (user: string) => void }) {
  const [username, setUsername] = useState("user1");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState<Notice>(idle);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setNotice({ kind: "loading", text: "Проверяем логин" });
    try {
      await api.login(username, password);
      onLogin(username);
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  return (
    <section className="login-shell">
      <form className="login-panel" onSubmit={submit}>
        <div>
          <p className="eyebrow">testovoe3</p>
          <h1>Вход в рабочую зону</h1>
        </div>
        <label>
          Пользователь
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
        </label>
        <label>
          Пароль
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
          />
        </label>
        <button disabled={notice.kind === "loading"} type="submit">
          <Check size={18} /> Войти
        </button>
        <StatusLine notice={notice} />
      </form>
    </section>
  );
}

function Workspace({ user, onLogout }: { user: string; onLogout: () => void }) {
  const [activeView, setActiveView] = useState<"workspace" | "history">("workspace");
  const [telegramStatus, setTelegramStatus] = useState<TelegramStatus | null>(null);
  const [sourceChannel, setSourceChannel] = useState("");
  const [targetChannel, setTargetChannel] = useState("");
  const [posts, setPosts] = useState<PostItem[]>([]);
  const [nextOffsetId, setNextOffsetId] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [notice, setNotice] = useState<Notice>(idle);
  const activePostsRequest = useRef<ActiveRequestRef["current"]>(null);

  const selected = useMemo(
    () => posts.find((post) => post.id === selectedId) ?? posts[0] ?? null,
    [posts, selectedId]
  );

  useEffect(() => {
    refreshTelegramStatus(setTelegramStatus);
  }, []);

  useEffect(() => {
    return () => activePostsRequest.current?.controller.abort();
  }, []);

  async function logout() {
    await api.logout();
    onLogout();
  }

  const handleSelectPost = useCallback((postId: number) => {
    setSelectedId(postId);
  }, []);

  const postKey = useCallback((_: number, post: PostItem) => post.id, []);

  const renderPost = useCallback(
    (_: number, post: PostItem) => (
      <PostRow
        active={post.id === selected?.id}
        onSelect={handleSelectPost}
        post={post}
      />
    ),
    [handleSelectPost, selected?.id]
  );

  async function loadPosts(offset?: number | null) {
    const normalizedSourceChannel = sourceChannel.trim();
    const normalizedTargetChannel = targetChannel.trim();
    const requestKey = [
      "posts",
      normalizedSourceChannel,
      normalizedTargetChannel,
      offset ?? "first"
    ].join(":");
    const request = beginExclusiveRequest(activePostsRequest, requestKey);
    if (request.status === "duplicate") {
      return;
    }

    setNotice({ kind: "loading", text: offset ? "Загружаем следующую страницу" : "Загружаем последние посты" });
    try {
      const page = await api.posts(normalizedSourceChannel, normalizedTargetChannel, offset, request.controller.signal);
      if (!isCurrentRequest(activePostsRequest, request.controller)) {
        return;
      }
      setPosts((current) => (offset ? [...current, ...page.items] : page.items));
      setSelectedId((current) => (offset ? current ?? page.items[0]?.id ?? null : page.items[0]?.id ?? null));
      setNextOffsetId(page.next_offset_id);
      setHasMore(page.has_more);
      setNotice({ kind: "success", text: page.message ?? "Посты загружены" });
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      setNotice({ kind: "error", text: errorMessage(error) });
    } finally {
      finishExclusiveRequest(activePostsRequest, request.controller);
    }
  }

  function updatePost(updated: PostItem) {
    setPosts((current) => current.map((post) => (post.id === updated.id ? updated : post)));
  }

  return (
    <section className="workspace">
      <header className="topbar">
        <div>
          <p className="eyebrow">Telegram Rewrite</p>
          <h1>Рабочая зона</h1>
        </div>
        <div className="topbar-actions">
          <div className="tabs" aria-label="Разделы">
            <button
              className={activeView === "workspace" ? "tab active" : "tab"}
              onClick={() => setActiveView("workspace")}
              type="button"
            >
              <RefreshCcw size={16} /> Рабочая зона
            </button>
            <button
              className={activeView === "history" ? "tab active" : "tab"}
              onClick={() => setActiveView("history")}
              type="button"
            >
              <History size={16} /> История
            </button>
          </div>
          <span>{user}</span>
          <button className="ghost" onClick={logout} type="button" title="Выйти">
            <LogOut size={18} /> Выйти
          </button>
        </div>
      </header>

      {activeView === "workspace" ? (
        <div className="layout">
          <aside className="side">
            <TelegramWizard status={telegramStatus} onChange={() => refreshTelegramStatus(setTelegramStatus)} />
            <section className="panel">
              <h2>Каналы</h2>
              <label>
                Исходный канал <span>для загрузки постов</span>
                <input value={sourceChannel} onChange={(event) => setSourceChannel(event.target.value)} placeholder="@source" />
              </label>
              <label>
                Канал для публикации <span>можно заполнить перед публикацией</span>
                <input value={targetChannel} onChange={(event) => setTargetChannel(event.target.value)} placeholder="@target" />
              </label>
              <p className="hint">Канал для публикации не влияет на загрузку постов. Права на публикацию проверяются при публикации.</p>
              <button
                disabled={!sourceChannel || notice.kind === "loading"}
                onClick={() => loadPosts(null)}
                type="button"
              >
                <RefreshCcw size={18} /> Загрузить посты
              </button>
              <StatusLine notice={notice} />
            </section>
          </aside>

          <section className="posts-column">
            <div className="posts-header">
              <h2>Посты</h2>
              <button
                className="secondary"
                disabled={!hasMore || !nextOffsetId || notice.kind === "loading"}
                onClick={() => loadPosts(nextOffsetId)}
                type="button"
              >
                <Plus size={18} /> Подгрузить ещё 10 постов
              </button>
            </div>
            <div className="post-list-shell">
              {posts.length ? (
                <Virtuoso
                  className="post-list"
                  computeItemKey={postKey}
                  data={posts}
                  itemContent={renderPost}
                  style={{ height: "100%" }}
                />
              ) : (
                <div className="empty">Здесь появятся текстовые посты из Telegram.</div>
              )}
            </div>
          </section>

          <PostEditor post={selected} targetChannel={targetChannel} onUpdated={updatePost} />
        </div>
      ) : (
        <HistoryView />
      )}
    </section>
  );
}

const PostRow = memo(function PostRow({
  active,
  onSelect,
  post
}: {
  active: boolean;
  onSelect: (postId: number) => void;
  post: PostItem;
}) {
  const select = useCallback(() => {
    onSelect(post.id);
  }, [onSelect, post.id]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onSelect(post.id);
      }
    },
    [onSelect, post.id]
  );

  return (
    <article
      className={active ? "post-row active" : "post-row"}
      onClick={select}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
    >
      <span className="post-row-id">#{post.telegram_message_id}</span>
      <div className={post.media_urls.length ? "post-row-body" : "post-row-body no-media"}>
        <MediaPreview urls={post.media_urls} compact />
        <p>{post.original_text}</p>
      </div>
    </article>
  );
});

function HistoryView() {
  const [items, setItems] = useState<PostItem[]>([]);
  const [notice, setNotice] = useState<Notice>({ kind: "loading", text: "Загружаем историю" });

  async function loadHistory() {
    setNotice({ kind: "loading", text: "Загружаем историю" });
    try {
      const history = await api.history();
      setItems(history.items);
      setNotice(history.items.length ? idle : { kind: "idle", text: "" });
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  useEffect(() => {
    loadHistory();
  }, []);

  return (
    <section className="history-view">
      <div className="history-header">
        <div>
          <h2>Обработанные посты</h2>
          <p className="hint">История рерайта и публикаций текущего аккаунта.</p>
        </div>
        <button className="secondary" onClick={loadHistory} type="button">
          <RefreshCcw size={18} /> Обновить
        </button>
      </div>
      <StatusLine notice={notice} />
      <div className="history-list">
        {items.map((post) => {
          const publishedMediaUrls =
            post.published_media_urls ?? (post.publish_status === "published" ? post.media_urls : []);
          return (
            <article className="history-item" key={post.id}>
              <div className="history-meta">
                <span className={`status-badge ${post.publish_status}`}>{publishStatusLabel(post.publish_status)}</span>
                <span>{post.source_channel} #{post.telegram_message_id}</span>
                <span>{post.target_channel ?? "target не указан"}</span>
              </div>
              <div className="history-grid">
                <section>
                  <h3>Основа</h3>
                  <MediaPreview urls={post.media_urls} />
                  <p>{post.original_text}</p>
                </section>
                <section>
                  <h3>Обработанный текст</h3>
                  <p>{post.rewritten_text ?? "Пока нет обработанного текста"}</p>
                  {post.publish_status === "published" && (
                    <div className="history-media">
                      <h3>Прикреплено к публикации</h3>
                      {post.published_url && (
                        <a className="published-link" href={post.published_url} target="_blank" rel="noreferrer">
                          Открыть опубликованный пост
                        </a>
                      )}
                      {publishedMediaUrls.length ? (
                        <MediaPreview urls={publishedMediaUrls} />
                      ) : (
                        <p className="hint">Без изображений</p>
                      )}
                    </div>
                  )}
                </section>
              </div>
              <div className="history-dates">
                <span>создан: {formatDate(post.created_at)}</span>
                <span>изменён: {formatDate(post.updated_at)}</span>
                <span>опубликован: {post.published_at ? formatDate(post.published_at) : "нет"}</span>
              </div>
              {post.error_message && <p className="error-text">{post.error_message}</p>}
            </article>
          );
        })}
        {items.length === 0 && notice.kind !== "loading" && (
          <div className="empty">Здесь появятся посты после рерайта или публикации.</div>
        )}
      </div>
    </section>
  );
}

function TelegramWizard({
  status,
  onChange
}: {
  status: TelegramStatus | null;
  onChange: () => void;
}) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<"credentials" | "code" | "password">("credentials");
  const [notice, setNotice] = useState<Notice>(idle);

  async function sendCode() {
    setNotice({ kind: "loading", text: "Отправляем код" });
    try {
      await api.telegramSendCode(phone);
      setStep("code");
      setNotice({ kind: "success", text: "Код отправлен" });
      onChange();
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  async function signIn() {
    setNotice({ kind: "loading", text: "Проверяем код" });
    try {
      const result = await api.telegramSignIn(code);
      if (result.password_required) {
        setStep("password");
        setNotice({ kind: "idle", text: "" });
      } else {
        setNotice({ kind: "success", text: "Telegram подключён" });
        onChange();
      }
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  async function sendPassword() {
    setNotice({ kind: "loading", text: "Проверяем 2FA" });
    try {
      await api.telegramPassword(password);
      setNotice({ kind: "success", text: "Telegram подключён" });
      onChange();
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  async function disconnect() {
    await api.telegramLogout();
    onChange();
  }

  return (
    <section className="panel">
      <div className="panel-title">
        <h2>Telegram</h2>
        {status?.connected && (
          <button className="icon-button" onClick={disconnect} type="button" title="Отключить Telegram">
            <Unplug size={18} />
          </button>
        )}
      </div>
      {status?.connected ? (
        <p className="connected">
          <Check size={16} /> Подключён {status.phone}
        </p>
      ) : (
        <div className="stack">
          {step === "credentials" && (
            <>
              <label>
                Phone
                <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+79990000000" />
              </label>
              <button disabled={!phone} onClick={sendCode} type="button">
                <Send size={18} /> Send code
              </button>
            </>
          )}
          {step === "code" && (
            <>
              <label>
                Code
                <input value={code} onChange={(event) => setCode(event.target.value)} />
              </label>
              <button disabled={!code} onClick={signIn} type="button">
                <Check size={18} /> Sign in
              </button>
            </>
          )}
          {step === "password" && (
            <>
              <label>
                2FA password
                <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
              </label>
              <button disabled={!password} onClick={sendPassword} type="button">
                <Check size={18} /> Confirm
              </button>
            </>
          )}
        </div>
      )}
      <StatusLine notice={notice} />
    </section>
  );
}

function PostEditor({
  post,
  targetChannel,
  onUpdated
}: {
  post: PostItem | null;
  targetChannel: string;
  onUpdated: (post: PostItem) => void;
}) {
  const [prompt, setPrompt] = useState("Перепиши пост живее и короче, сохрани смысл.");
  const [text, setText] = useState("");
  const [includeOriginalMedia, setIncludeOriginalMedia] = useState(true);
  const [customMediaUrls, setCustomMediaUrls] = useState<string[]>([]);
  const [notice, setNotice] = useState<Notice>(idle);
  const selectedMediaUrls = useMemo(
    () => [
      ...(includeOriginalMedia && post ? post.media_urls : []),
      ...customMediaUrls
    ],
    [customMediaUrls, includeOriginalMedia, post]
  );
  const duplicatePublish =
    Boolean(post && post.publish_status === "published") &&
    sameChannel(post?.target_channel, targetChannel) &&
    (post?.rewritten_text ?? "").trim() === text.trim() &&
    sameStringList(post?.published_media_urls ?? [], selectedMediaUrls);

  useEffect(() => {
    setText(post?.rewritten_text ?? "");
    setIncludeOriginalMedia(Boolean(post?.media_urls.length));
    setCustomMediaUrls([]);
    setNotice(idle);
  }, [post?.id]);

  async function rewrite() {
    if (!post) return;
    setNotice({ kind: "loading", text: "Рерайт через DeepSeek" });
    try {
      const updated = await api.rewrite(post.id, prompt);
      onUpdated(updated);
      setText(updated.rewritten_text ?? "");
      setNotice({ kind: "success", text: "Готово" });
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  async function publish() {
    if (!post) return;
    setNotice({ kind: "loading", text: "Публикуем" });
    try {
      const updated = await api.publish(post.id, targetChannel, text, selectedMediaUrls);
      onUpdated(updated);
      setText(updated.rewritten_text ?? text);
      setNotice({ kind: "success", text: "Опубликовано" });
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  async function uploadMedia(files: FileList | null) {
    if (!post || !files?.length) return;
    const selectedFiles = Array.from(files);
    if (customMediaUrls.length + selectedFiles.length > 2) {
      setNotice({ kind: "error", text: "Можно добавить не больше двух своих изображений" });
      return;
    }

    setNotice({ kind: "loading", text: "Загружаем изображения" });
    try {
      const response = await api.uploadMedia(post.id, selectedFiles);
      setCustomMediaUrls((current) => [...current, ...response.media_urls].slice(0, 2));
      setNotice({ kind: "success", text: "Изображения загружены" });
    } catch (error) {
      setNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  return (
    <section className="editor">
      <h2>Рерайт и публикация</h2>
      {post ? (
        <>
          <label>
            Оригинал
            <textarea value={post.original_text} readOnly rows={7} />
          </label>
          <MediaPreview urls={post.media_urls} />
          <section className="media-controls" aria-label="Медиа для публикации">
            {post.media_urls.length > 0 && (
              <label className="media-toggle">
                <input
                  checked={includeOriginalMedia}
                  onChange={(event) => setIncludeOriginalMedia(event.target.checked)}
                  type="checkbox"
                />
                Публиковать изображение из оригинального поста
              </label>
            )}
            <label className="file-picker">
              <ImagePlus size={18} />
              Добавить свои изображения
              <input
                accept="image/*"
                disabled={customMediaUrls.length >= 2 || notice.kind === "loading"}
                multiple
                onChange={(event) => {
                  void uploadMedia(event.target.files);
                  event.target.value = "";
                }}
                type="file"
              />
            </label>
            <p className="hint">Можно добавить до двух своих изображений.</p>
            <EditableMediaPreview
              urls={customMediaUrls}
              onRemove={(url) => setCustomMediaUrls((current) => current.filter((item) => item !== url))}
            />
          </section>
          <label>
            Промпт
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={4} />
          </label>
          <button disabled={!prompt || notice.kind === "loading"} onClick={rewrite} type="button">
            <Sparkles size={18} /> Переписать
          </button>
          <label>
            Результат
            <textarea value={text} onChange={(event) => setText(event.target.value)} rows={9} />
          </label>
          {!targetChannel && <p className="hint">Введите канал для публикации, когда будете готовы публиковать.</p>}
          {duplicatePublish && (
            <p className="hint">
              Этот вариант уже опубликован. Измените текст, канал или изображения, чтобы опубликовать заново.
            </p>
          )}
          <button
            disabled={!text.trim() || !targetChannel || duplicatePublish || notice.kind === "loading"}
            onClick={publish}
            type="button"
          >
            <Send size={18} /> Опубликовать
          </button>
          <StatusLine notice={notice} />
          {post.published_url && (
            <a className="published-link" href={post.published_url} target="_blank" rel="noreferrer">
              Открыть опубликованный пост
            </a>
          )}
          {post.error_message && <p className="error-text">{post.error_message}</p>}
        </>
      ) : (
        <div className="empty">Выберите пост для рерайта.</div>
      )}
    </section>
  );
}

function EditableMediaPreview({ urls, onRemove }: { urls: string[]; onRemove: (url: string) => void }) {
  if (!urls.length) return null;
  return (
    <div className="editable-media-grid">
      {urls.map((url) => (
        <div className="editable-media-item" key={url}>
          <img alt="Custom post media" src={url} loading="lazy" />
          <button className="icon-button" onClick={() => onRemove(url)} type="button" title="Убрать изображение">
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}

function MediaPreview({ urls, compact = false }: { urls: string[]; compact?: boolean }) {
  if (!urls.length) return null;
  return (
    <div className={compact ? "media-grid compact" : "media-grid"}>
      {urls.map((url) => (
        <img alt="Telegram post media" key={url} src={url} loading="lazy" />
      ))}
    </div>
  );
}

function StatusLine({ notice }: { notice: Notice }) {
  if (!notice.text) return null;
  return <p className={`status ${notice.kind}`}>{notice.text}</p>;
}

function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return "Неизвестная ошибка";
  }
  if (error.message === "duplicate_publish") {
    return "Этот вариант уже опубликован. Измените текст, канал или изображения.";
  }
  return error.message;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
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

function publishStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    fetched: "загружен",
    rewritten: "переписан",
    published: "опубликован",
    rewrite_error: "ошибка рерайта",
    publish_error: "ошибка публикации",
    error: "ошибка"
  };
  return labels[status] ?? status;
}

async function refreshTelegramStatus(setTelegramStatus: (status: TelegramStatus) => void) {
  try {
    setTelegramStatus(await api.telegramStatus());
  } catch {
    setTelegramStatus({ connected: false, phone: null, needs_credentials: true });
  }
}

export default App;
