import React from 'react';

interface TopicCoverage {
  topic: string;
  books: Array<{
    book_id: string;
    section_id?: string;
    heading?: string;
    confidence: 'high' | 'medium' | 'low';
    score: number;
  }>;
  covered: boolean;
}

interface CoverageMatrixProps {
  coverageMatrix: TopicCoverage[];
  gaps: TopicCoverage[];
}

export function CoverageMatrix({ coverageMatrix, gaps }: CoverageMatrixProps) {
  const getConfidenceColor = (confidence: string) => {
    switch (confidence) {
      case 'high': return '#10b981';
      case 'medium': return '#f59e0b';
      case 'low': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const coveragePercentage = coverageMatrix.length > 0
    ? (coverageMatrix.filter(c => c.covered).length / coverageMatrix.length) * 100
    : 0;

  return (
    <div className="coverage-matrix">
      <div className="coverage-header">
        <h2>Coverage Matrix</h2>
        <div className="coverage-stats">
          <span className="coverage-percentage">{coveragePercentage.toFixed(1)}% covered</span>
          <span className="coverage-detail">
            {coverageMatrix.filter(c => c.covered).length} / {coverageMatrix.length} topics
          </span>
        </div>
      </div>

      {gaps.length > 0 && (
        <div className="gaps-section">
          <h3>Uncovered Topics</h3>
          <ul className="gaps-list">
            {gaps.map((gap, idx) => (
              <li key={idx} className="gap-item">{gap.topic}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="matrix-table">
        <table>
          <thead>
            <tr>
              <th>Topic</th>
              <th>Coverage</th>
              <th>Sources</th>
            </tr>
          </thead>
          <tbody>
            {coverageMatrix.map((item, idx) => (
              <tr key={idx} className={!item.covered ? 'uncovered' : ''}>
                <td className="topic-cell">{item.topic}</td>
                <td className="coverage-cell">
                  {item.covered ? (
                    <span className="covered-badge">Covered</span>
                  ) : (
                    <span className="uncovered-badge">Not Found</span>
                  )}
                </td>
                <td className="sources-cell">
                  <div className="confidence-bars">
                    {item.books.map((book, bIdx) => (
                      <div key={bIdx} className="confidence-item">
                        <span className="book-id">{book.book_id}</span>
                        <div
                          className="confidence-bar"
                          style={{
                            backgroundColor: getConfidenceColor(book.confidence),
                            width: `${book.score * 100}%`,
                          }}
                        />
                        <span className="confidence-label">{book.confidence}</span>
                      </div>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
