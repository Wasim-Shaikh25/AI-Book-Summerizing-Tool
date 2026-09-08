import { FormEvent, useEffect, useRef, useState } from "react";

import {

  apiFetch,

  sendMessageStream,

  statusLabel,

  uploadBookWithProgress,

  type BookSummary,

  type ConversationSummary,

  type Message,

} from "../auth/api";

import { useAuth } from "../auth/AuthProvider";

import { MessageBubble } from "./components/MessageBubble";

import { Sidebar, WelcomePanel } from "./components/Sidebar";



export function ChatApp() {

  const { user, logout } = useAuth();

  const [books, setBooks] = useState<BookSummary[]>([]);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  const [activeConvId, setActiveConvId] = useState<string | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);

  const [input, setInput] = useState("");

  const [sending, setSending] = useState(false);

  const [statusText, setStatusText] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);

  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  const fileRef = useRef<HTMLInputElement>(null);



  const loadBooks = async () => {

    const data = await apiFetch<BookSummary[]>("/api/books");

    setBooks(data);

    return data;

  };



  const loadConversations = async () => {

    const data = await apiFetch<ConversationSummary[]>("/api/conversations");

    setConversations(data);

    return data;

  };



  const loadMessages = async (convId: string) => {

    const data = await apiFetch<Message[]>(`/api/conversations/${convId}/messages`);

    setMessages(data);

  };



  useEffect(() => {

    void (async () => {

      await loadBooks();

      const convs = await loadConversations();

      if (convs.length > 0) {

        setActiveConvId((prev) => prev ?? convs[0].conversation_id);

      }

    })();

  }, []);



  useEffect(() => {

    if (activeConvId) loadMessages(activeConvId);

  }, [activeConvId]);



  useEffect(() => {

    bottomRef.current?.scrollIntoView({ behavior: "smooth" });

  }, [messages, sending]);



  const openFilePicker = () => fileRef.current?.click();



  const handleUpload = async (file: File) => {

    if (!file.name.toLowerCase().endsWith(".pdf")) {

      setError("Please choose a PDF file.");

      return;

    }

    setUploading(true);

    setUploadStatus("Uploading file...");

    setError(null);

    try {

      const book = await uploadBookWithProgress(file, (msg) => setUploadStatus(msg));

      await loadBooks();

      const conv = await apiFetch<ConversationSummary>("/api/conversations", {

        method: "POST",

        body: JSON.stringify({ book_id: book.book_id, title: book.title }),

      });

      await loadConversations();

      setActiveConvId(conv.conversation_id);

      setMessages([]);

    } catch (e) {

      setError(e instanceof Error ? e.message : "Upload failed");

    } finally {

      setUploading(false);

      setUploadStatus(null);

    }

  };



  const handleNewChat = async () => {

    setError(null);

    const latestBooks = books.length ? books : await loadBooks();

    if (!latestBooks.length) {

      setError("Upload a PDF first.");

      openFilePicker();

      return;

    }

    const book = latestBooks[0];

    const conv = await apiFetch<ConversationSummary>("/api/conversations", {

      method: "POST",

      body: JSON.stringify({ book_id: book.book_id, title: "New chat" }),

    });

    await loadConversations();

    setActiveConvId(conv.conversation_id);

    setMessages([]);

  };



  const handleSend = async (e: FormEvent) => {

    e.preventDefault();

    if (!input.trim() || !activeConvId || sending) return;



    const text = input.trim();

    setInput("");

    setSending(true);

    setError(null);

    setStatusText("Sending...");



    const optimistic: Message = {

      message_id: `tmp-${Date.now()}`,

      role: "user",

      content: text,

      created_at: new Date().toISOString(),

    };

    setMessages((prev) => [...prev, optimistic]);



    try {

      const res = await sendMessageStream(activeConvId, text, (status) => {

        setStatusText(statusLabel(status.stage));

      });

      setMessages((prev) => [...prev, res.assistant_message]);

      await loadConversations();

    } catch (e) {

      setError(e instanceof Error ? e.message : "Send failed");

    } finally {

      setSending(false);

      setStatusText(null);

    }

  };



  const activeTitle =

    conversations.find((c) => c.conversation_id === activeConvId)?.title ?? "Chat";



  return (

    <div className="app-shell">

      <input

        ref={fileRef}

        type="file"

        accept=".pdf,application/pdf"

        hidden

        onChange={(e) => {

          const f = e.target.files?.[0];

          if (f) void handleUpload(f);

          e.target.value = "";

        }}

      />



      <Sidebar

        conversations={conversations}

        activeId={activeConvId}

        onSelect={setActiveConvId}

        onNewChat={() => void handleNewChat()}

        onUploadClick={openFilePicker}

        uploading={uploading}

      />



      <main className="chat-main">

        <header className="chat-header">

          <div>

            <h2>{activeConvId ? activeTitle : "Upload a PDF to start"}</h2>

            {user && <span className="user-badge">{user.display_name}</span>}

          </div>

          <div className="header-actions">

            <button

              type="button"

              className="primary-btn header-upload-btn"

              onClick={openFilePicker}

              disabled={uploading}

            >

              {uploading ? "Uploading..." : "Upload PDF"}

            </button>

            <button type="button" className="ghost-btn" onClick={logout}>

              Sign out

            </button>

          </div>

        </header>



        <div className="messages-panel">

          {!activeConvId && (

            <WelcomePanel

              onUploadClick={openFilePicker}

              onNewChat={() => void handleNewChat()}

              onDropFile={(f) => void handleUpload(f)}

              uploading={uploading}

              hasBooks={books.length > 0}

            />

          )}

          {messages.map((m) => (

            <MessageBubble key={m.message_id} message={m} />

          ))}

          {sending && (

            <div className="typing-indicator">

              <span /><span /><span />

              {statusText && <p className="status-text">{statusText}</p>}

            </div>

          )}

          <div ref={bottomRef} />

        </div>



        {error && <div className="error-banner">{error}</div>}



        {uploading && uploadStatus && (

          <div className="upload-progress-banner">

            <div className="upload-progress-spinner" />

            <div>

              <strong>Processing PDF</strong>

              <p>{uploadStatus}</p>

              <span className="upload-progress-note">Large books can take several minutes — please keep this tab open.</span>

            </div>

          </div>

        )}



        {!activeConvId ? (

          <div className="composer composer-hint">

            <p>Upload a PDF above to enable the chat box.</p>

          </div>

        ) : (

          <form className="composer" onSubmit={handleSend}>

            <textarea

              value={input}

              onChange={(e) => setInput(e.target.value)}

              placeholder="Ask a question, request rewrite, or say 'give me word file'..."

              disabled={sending}

              rows={2}

              autoFocus

              onKeyDown={(e) => {

                if (e.key === "Enter" && !e.shiftKey) {

                  e.preventDefault();

                  void handleSend(e);

                }

              }}

            />

            <button type="submit" disabled={sending || !input.trim()}>

              Send

            </button>

          </form>

        )}

      </main>

    </div>

  );

}



export default ChatApp;

