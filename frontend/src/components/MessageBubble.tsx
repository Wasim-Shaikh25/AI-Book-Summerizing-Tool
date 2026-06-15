import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { downloadFile, type Message } from "../../auth/api";

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const downloadUrl = message.metadata?.docx_download_url;
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    if (!downloadUrl) return;
    setDownloading(true);
    setError(null);
    try {
      await downloadFile(downloadUrl);
    } catch {
      setError("Download failed. Please try again.");
    } finally {
      setDownloading(false);
    }
  };

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
          <>
            <button
              type="button"
              className="download-btn"
              onClick={() => void handleDownload()}
              disabled={downloading}
            >
              {downloading ? "Preparing..." : "Download Word file"}
            </button>
            {error && <p className="download-error">{error}</p>}
          </>
        )}
      </div>
    </div>
  );
}
