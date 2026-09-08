"""Executor agent for running execution plans and managing tool calls."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
import logging

from .tool_registry import ToolRegistry, ToolDefinition
from .planner_agent import ExecutionPlan, ExecutionStep, StepType

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Status of step execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepResult(BaseModel):
    """Result of executing a single step."""
    step_id: str
    status: ExecutionStatus
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0


class ExecutionResult(BaseModel):
    """Result of executing an entire plan."""
    plan_id: str
    status: ExecutionStatus
    step_results: List[StepResult] = Field(default_factory=list)
    final_output: Optional[Dict[str, Any]] = None
    total_execution_time: float = 0.0
    errors: List[str] = Field(default_factory=list)
    steps_completed: int = 0
    steps_failed: int = 0


class ExecutorAgent:
    """Agent that executes plans by calling tools in sequence."""
    
    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self.state: Dict[str, Any] = {}  # Execution state for passing data between steps
    
    def execute_plan(self, plan: ExecutionPlan) -> ExecutionResult:
        """Execute an execution plan."""
        logger.info(f"Executing plan: {plan.plan_id}")
        logger.info(f"User request: {plan.user_request}")
        logger.info(f"Estimated steps: {plan.estimated_steps}")
        
        if plan.requires_user_input:
            return ExecutionResult(
                plan_id=plan.plan_id,
                status=ExecutionStatus.FAILED,
                errors=plan.missing_information,
                final_output={
                    "status": "requires_input",
                    "missing_information": plan.missing_information,
                    "message": plan.reasoning
                }
            )
        
        step_results = []
        errors = []
        total_time = 0.0
        
        # Execute steps in dependency order
        executed_steps = set()
        
        for iteration in range(len(plan.steps) * 2):  # Prevent infinite loops
            progress_made = False
            
            for step in plan.steps:
                if step.step_id in executed_steps:
                    continue
                
                # Check if dependencies are satisfied
                dependencies_met = all(dep in executed_steps for dep in step.depends_on)
                if not dependencies_met:
                    continue
                
                # Execute the step
                result = self._execute_step(step)
                step_results.append(result)
                
                if result.status == ExecutionStatus.COMPLETED:
                    executed_steps.add(step.step_id)
                    # Store output in state for dependent steps
                    if result.output:
                        self.state[step.step_id] = result.output
                    progress_made = True
                elif result.status == ExecutionStatus.FAILED:
                    errors.append(f"Step {step.step_id} failed: {result.error}")
                    # Continue execution if possible, or fail if critical
                    if step.step_type == StepType.TOOL_CALL:
                        # Non-critical, continue
                        executed_steps.add(step.step_id)
                        progress_made = True
                    else:
                        # Critical step failed
                        total_time += sum(r.execution_time for r in step_results)
                        return ExecutionResult(
                            plan_id=plan.plan_id,
                            status=ExecutionStatus.FAILED,
                            step_results=step_results,
                            errors=errors,
                            total_execution_time=total_time
                        )
            
            if not progress_made:
                break  # No more progress can be made
        
        # Check if all steps were executed
        if len(executed_steps) < len(plan.steps):
            missing_steps = [s.step_id for s in plan.steps if s.step_id not in executed_steps]
            errors.append(f"Could not execute steps: {missing_steps}")
        
        total_time = sum(r.execution_time for r in step_results)
        
        # Determine final status
        status = ExecutionStatus.COMPLETED if not errors else ExecutionStatus.FAILED
        
        # Compile final output from state
        final_output = self._compile_final_output(plan, step_results)
        
        # Count completed and failed steps
        steps_completed = len([r for r in step_results if r.status == ExecutionStatus.COMPLETED])
        steps_failed = len([r for r in step_results if r.status == ExecutionStatus.FAILED])
        
        return ExecutionResult(
            plan_id=plan.plan_id,
            status=status,
            step_results=step_results,
            final_output=final_output,
            total_execution_time=total_time,
            errors=errors,
            steps_completed=steps_completed,
            steps_failed=steps_failed
        )
    
    def _execute_step(self, step: ExecutionStep) -> StepResult:
        """Execute a single step."""
        import time
        start_time = time.time()
        
        logger.info(f"Executing step: {step.step_id} - {step.description}")
        
        try:
            if step.step_type == StepType.TOOL_CALL:
                result = self._execute_tool_call(step)
            elif step.step_type == StepType.CONDITIONAL:
                result = self._execute_conditional(step)
            elif step.step_type == StepType.PARALLEL:
                result = self._execute_parallel(step)
            elif step.step_type == StepType.LOOP:
                result = self._execute_loop(step)
            else:
                result = StepResult(
                    step_id=step.step_id,
                    status=ExecutionStatus.FAILED,
                    error=f"Unknown step type: {step.step_type}"
                )
        except Exception as e:
            logger.error(f"Error executing step {step.step_id}: {e}")
            result = StepResult(
                step_id=step.step_id,
                status=ExecutionStatus.FAILED,
                error=str(e)
            )
        
        execution_time = time.time() - start_time
        result.execution_time = execution_time
        
        logger.info(f"Step {step.step_id} completed with status: {result.status}")
        
        return result
    
    def _execute_tool_call(self, step: ExecutionStep) -> StepResult:
        """Execute a tool call step."""
        tool = self.tool_registry.get_tool(step.tool_name)
        
        if not tool:
            return StepResult(
                step_id=step.step_id,
                status=ExecutionStatus.FAILED,
                error=f"Tool not found: {step.tool_name}"
            )
        
        # Resolve parameters that reference previous step outputs
        resolved_parameters = self._resolve_parameters(step.parameters)
        
        # Call the tool function
        try:
            output = tool.function(**resolved_parameters)
            return StepResult(
                step_id=step.step_id,
                status=ExecutionStatus.COMPLETED,
                output=output
            )
        except Exception as e:
            return StepResult(
                step_id=step.step_id,
                status=ExecutionStatus.FAILED,
                error=f"Tool execution failed: {str(e)}"
            )
    
    def _execute_conditional(self, step: ExecutionStep) -> StepResult:
        """Execute a conditional step."""
        # For now, skip conditional logic
        return StepResult(
            step_id=step.step_id,
            status=ExecutionStatus.SKIPPED,
            error="Conditional logic not yet implemented"
        )
    
    def _execute_parallel(self, step: ExecutionStep) -> StepResult:
        """Execute parallel steps."""
        # For now, execute sequentially
        return StepResult(
            step_id=step.step_id,
            status=ExecutionStatus.SKIPPED,
            error="Parallel execution not yet implemented"
        )
    
    def _execute_loop(self, step: ExecutionStep) -> StepResult:
        """Execute a loop step."""
        # For now, skip loop logic
        return StepResult(
            step_id=step.step_id,
            status=ExecutionStatus.SKIPPED,
            error="Loop logic not yet implemented"
        )
    
    def _resolve_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve parameters that may reference previous step outputs."""
        resolved = {}
        
        for key, value in parameters.items():
            if isinstance(value, str) and value.startswith("$"):
                # Reference to previous step output
                reference = value[1:]  # Remove $ prefix
                if reference in self.state:
                    resolved[key] = self.state[reference]
                else:
                    logger.warning(f"Reference not found in state: {reference}")
                    resolved[key] = value
            else:
                resolved[key] = value
        
        return resolved
    
    def _compile_final_output(self, plan: ExecutionPlan, step_results: List[StepResult]) -> Dict[str, Any]:
        """Compile final output from step results."""
        output = {
            "plan_id": plan.plan_id,
            "user_request": plan.user_request,
            "steps_completed": len([r for r in step_results if r.status == ExecutionStatus.COMPLETED]),
            "steps_failed": len([r for r in step_results if r.status == ExecutionStatus.FAILED]),
            "reasoning": plan.reasoning
        }
        
        # Collect outputs from completed steps
        outputs = {}
        for result in step_results:
            if result.status == ExecutionStatus.COMPLETED and result.output:
                outputs[result.step_id] = result.output
        
        output["step_outputs"] = outputs
        
        # Try to determine the most relevant output based on plan type
        if "study_guide" in plan.plan_id.lower():
            # Look for export step output
            for step_id, step_output in outputs.items():
                if "export" in step_id.lower() and step_output:
                    output["final_result"] = step_output
                    break
        elif "qa" in plan.plan_id.lower():
            # Look for answer outputs
            answers = {}
            for step_id, step_output in outputs.items():
                if "answer" in step_id.lower() and step_output:
                    answers[step_id] = step_output
            output["final_result"] = answers
        else:
            # Use the last successful output
            if outputs:
                last_step_id = list(outputs.keys())[-1]
                output["final_result"] = outputs[last_step_id]
        
        return output
