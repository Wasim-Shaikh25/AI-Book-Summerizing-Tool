import ReactMarkdown from "react-markdown";
import type { Message } from "../../auth/api";

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const downloadUrl = message.metadata?.docx_download_url;

  return (
    <div className={`message-row ${isUser ? "user" : "assistant"}`}>
      <div className="message-avatar">{isUser ? "You" : "AI"}</div>
      <div className="message-body">
        <div className="message-content">
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <ReactMarkdown>{message.content}</ReactMarkdown>
          )}
        </div>
        {downloadUrl && (
          <a
            className="download-btn"
            href={downloadUrl}
            target="_blank"
            rel="noreferrer"
          >
            Download Word file
          </a>
        )}
      </div>
    </div>
  );
}
