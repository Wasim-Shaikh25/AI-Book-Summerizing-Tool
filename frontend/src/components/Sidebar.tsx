import { useRef, type DragEvent } from "react";
import type { ConversationSummary } from "../../auth/api";

interface Props {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onUploadClick: () => void;
  uploading: boolean;
}

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onUploadClick,
  uploading,
}: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="logo-mark small">AI</span>
        <span>Notes Creator</span>
      </div>

      <div className="sidebar-header">
        <button type="button" className="primary-btn" onClick={onUploadClick} disabled={uploading}>
          {uploading ? "Uploading PDF..." : "Upload PDF"}
        </button>
        <button type="button" className="secondary-btn" onClick={onNewChat}>
          + New chat
        </button>
      </div>

      <div className="conversation-list">
        {conversations.length === 0 && (
          <p className="empty-hint">No chats yet. Upload a PDF to begin.</p>
        )}
        {conversations.map((c) => (
          <button
            key={c.conversation_id}
            type="button"
            className={`conversation-item ${activeId === c.conversation_id ? "active" : ""}`}
            onClick={() => onSelect(c.conversation_id)}
          >
            <span className="conv-title">{c.title}</span>
            <span className="conv-date">
              {new Date(c.updated_at).toLocaleDateString()}
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}

interface WelcomeProps {
  onUploadClick: () => void;
  onNewChat: () => void;
  onDropFile: (file: File) => void;
  uploading: boolean;
  hasBooks: boolean;
}

export function WelcomePanel({
  onUploadClick,
  onNewChat,
  onDropFile,
  uploading,
  hasBooks,
}: WelcomeProps) {
  const dragDepth = useRef(0);

  const onDragEnter = (e: DragEvent) => {
    e.preventDefault();
    dragDepth.current += 1;
  };

  const onDragLeave = (e: DragEvent) => {
    e.preventDefault();
    dragDepth.current -= 1;
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    dragDepth.current = 0;
    const file = e.dataTransfer.files?.[0];
    if (file) onDropFile(file);
  };

  return (
    <div
      className="welcome-panel"
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      <h3>Get started</h3>
      <p>Upload a PDF book to ask questions, rewrite notes, or export Word files.</p>

      <div className="welcome-actions">
        <button
          type="button"
          className="primary-btn welcome-upload-btn"
          onClick={onUploadClick}
          disabled={uploading}
        >
          {uploading ? "Uploading..." : "Upload PDF"}
        </button>
        {hasBooks && (
          <button type="button" className="secondary-btn" onClick={onNewChat}>
            Start chat with existing book
          </button>
        )}
      </div>

      <div className="drop-zone">
        <strong>Drag &amp; drop a PDF here</strong>
        <span>or use the Upload PDF button</span>
      </div>

      <ul>
        <li>Full PDF rewrite always gives a Word download</li>
        <li>Short Q&amp;A stays in chat</li>
        <li>Long answers auto-export to Word</li>
        <li>Say &quot;give me word file&quot; anytime</li>
      </ul>
    </div>
  );
}
