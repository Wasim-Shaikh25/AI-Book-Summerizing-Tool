import React from 'react';

interface ToolCall {
  tool_name: string;
  description: string;
  is_write: boolean;
  is_batch: boolean;
  estimated_cost_seconds: number;
  input_summary: string;
}

interface PlanData {
  plan_id: string;
  reasoning: string;
  requires_approval: boolean;
  estimated_cost_seconds: number;
  estimated_time_human: string;
  tool_count: number;
  tools: ToolCall[];
}

interface PlanApprovalUIProps {
  plan: PlanData;
  onApprove: (approved: boolean) => void;
}

export function PlanApprovalUI({ plan, onApprove }: PlanApprovalUIProps) {
  return (
    <div className="plan-approval">
      <div className="plan-header">
        <h2>Plan Approval Required</h2>
        <span className="plan-id">{plan.plan_id}</span>
      </div>

      <div className="plan-reasoning">
        <h3>Reasoning</h3>
        <p>{plan.reasoning}</p>
      </div>

      <div className="plan-tools">
        <h3>Planned Actions ({plan.tool_count})</h3>
        <div className="tool-list">
          {plan.tools.map((tool, idx) => (
            <div key={idx} className="tool-item">
              <div className="tool-header">
                <span className="tool-name">{tool.tool_name}</span>
                <div className="tool-badges">
                  {tool.is_write && <span className="badge write">Write</span>}
                  {tool.is_batch && <span className="badge batch">Batch</span>}
                </div>
              </div>
              <p className="tool-description">{tool.description}</p>
              <p className="tool-input">Input: {tool.input_summary}</p>
              <p className="tool-cost">Est. time: {tool.estimated_cost_seconds}s</p>
            </div>
          ))}
        </div>
      </div>

      <div className="plan-summary">
        <div className="summary-item">
          <span className="label">Total estimated time:</span>
          <span className="value">{plan.estimated_time_human}</span>
        </div>
        <div className="summary-item">
          <span className="label">Total actions:</span>
          <span className="value">{plan.tool_count}</span>
        </div>
      </div>

      <div className="plan-actions">
        <button
          onClick={() => onApprove(true)}
          className="approve-btn"
        >
          Approve Plan
        </button>
        <button
          onClick={() => onApprove(false)}
          className="reject-btn"
        >
          Reject Plan
        </button>
      </div>
    </div>
  );
}
