import React, { useState, useEffect } from 'react';

interface JobProgressProps {
  jobId: string;
  onComplete?: (result: any) => void;
}

export function JobProgress({ jobId, onComplete }: JobProgressProps) {
  const [status, setStatus] = useState<string>('pending');
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    pollJobStatus();
    const interval = setInterval(pollJobStatus, 2000);
    return () => clearInterval(interval);
  }, [jobId]);

  const pollJobStatus = async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      const data = await response.json();
      setStatus(data.status);
      setProgress(data.progress || 0);
      setMessage(data.message || '');
      setError(data.error || null);

      if (data.status === 'done') {
        onComplete?.(data.result);
      } else if (data.status === 'error') {
        setError(data.error || 'Job failed');
      }
    } catch (err) {
      setError('Failed to fetch job status');
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case 'done': return '#10b981';
      case 'error': return '#ef4444';
      case 'running': return '#3b82f6';
      default: return '#6b7280';
    }
  };

  return (
    <div className="job-progress">
      <div className="job-header">
        <h3>Job Progress</h3>
        <span className="job-id">{jobId}</span>
      </div>

      {error ? (
        <div className="job-error">
          <p>{error}</p>
        </div>
      ) : (
        <>
          <div className="progress-bar-container">
            <div className="progress-bar" style={{ width: `${progress}%`, backgroundColor: getStatusColor() }} />
          </div>
          <div className="progress-info">
            <span className="progress-percent">{progress}%</span>
            <span className="progress-message">{message}</span>
            <span className="progress-status" style={{ color: getStatusColor() }}>
              {status}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
