import React, { useState } from 'react';

interface Citation {
  section_id?: string;
  heading?: string;
  page?: number;
  book_id?: string;
}

interface CitationPanelProps {
  citations: Citation[];
  onClose?: () => void;
}

export function CitationPanel({ citations, onClose }: CitationPanelProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className={`citation-panel ${expanded ? 'expanded' : 'collapsed'}`}>
      <div className="citation-header">
        <h3>Citations</h3>
        <div className="citation-controls">
          <button onClick={() => setExpanded(!expanded)} className="toggle-btn">
            {expanded ? '−' : '+'}
          </button>
          {onClose && (
            <button onClick={onClose} className="close-btn">
              ×
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="citation-content">
          <p className="citation-count">{citations.length} sources</p>
          <ul className="citation-list">
            {citations.map((citation, idx) => (
              <li key={idx} className="citation-item">
                <div className="citation-main">
                  {citation.heading && (
                    <span className="citation-heading">{citation.heading}</span>
                  )}
                  {citation.book_id && (
                    <span className="citation-book">({citation.book_id})</span>
                  )}
                </div>
                <div className="citation-meta">
                  {citation.section_id && (
                    <span className="citation-section">§ {citation.section_id}</span>
                  )}
                  {citation.page && (
                    <span className="citation-page">p. {citation.page}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
