"""Test script for the agentic conversational system."""

import sys
from pathlib import Path

# Add backend to path
backend_root = Path(__file__).parent
sys.path.insert(0, str(backend_root))

from src.modules.agent.conversational_agent import get_conversational_agent
from src.modules.agent.tool_registry import get_tool_registry


def test_basic_conversation():
    """Test basic conversation flow."""
    print("=" * 60)
    print("TEST: Basic Conversation Flow")
    print("=" * 60)
    
    agent = get_conversational_agent()
    
    # Test 1: Simple question
    print("\nUser: What can you help me with?")
    response = agent.process_message("What can you help me with?")
    print(f"Agent: {response.message}")
    print(f"Plan ID: {response.plan_id}")
    print(f"Status: {response.execution_result.status if response.execution_result else 'N/A'}")
    
    # Test 2: Document processing request
    print("\nUser: I want to process a PDF document")
    response = agent.process_message("I want to process a PDF document")
    print(f"Agent: {response.message}")
    print(f"Requires Action: {response.requires_action}")
    if response.requires_action:
        print(f"Action Type: {response.action_type}")
        print(f"Action Details: {response.action_details}")
    
    # Test 3: Study guide creation
    print("\nUser: Create a study guide from my documents")
    response = agent.process_message("Create a study guide from my documents")
    print(f"Agent: {response.message}")
    print(f"Plan ID: {response.plan_id}")
    
    return True


def test_tool_registry():
    """Test tool registry functionality."""
    print("\n" + "=" * 60)
    print("TEST: Tool Registry")
    print("=" * 60)
    
    registry = get_tool_registry()
    
    # List all tools
    tools = registry.list_tools()
    print(f"\nTotal tools available: {len(tools)}")
    
    for tool in tools:
        print(f"\n- {tool.name} ({tool.category})")
        print(f"  Description: {tool.description}")
        print(f"  Parameters: {len(tool.parameters)}")
    
    # Get tool schemas for LLM
    schemas = registry.get_tool_schema()
    print(f"\nTool schemas for LLM: {len(schemas)}")
    
    return True


def test_planning():
    """Test planning capabilities."""
    print("\n" + "=" * 60)
    print("TEST: Planning Capabilities")
    print("=" * 60)
    
    agent = get_conversational_agent()
    
    test_requests = [
        "Process this PDF and create study notes",
        "I have 2 textbooks and 5 question papers. Create a study guide.",
        "What are the main topics in my documents?",
        "Answer these questions about the constitution"
    ]
    
    for request in test_requests:
        print(f"\nRequest: {request}")
        response = agent.process_message(request)
        print(f"Response: {response.message}")
        if response.plan_id:
            print(f"Plan created: {response.plan_id}")
    
    return True


def test_multi_document_scenario():
    """Test multi-document workflow scenario."""
    print("\n" + "=" * 60)
    print("TEST: Multi-Document Scenario")
    print("=" * 60)
    
    agent = get_conversational_agent()
    
    # Simulate document upload
    print("\nSimulating document upload...")
    response = agent.upload_document(
        file_path="test.pdf",
        file_name="Constitution.pdf",
        file_type="pdf"
    )
    print(f"Agent: {response.message}")
    
    # Create study guide request
    print("\nUser: Create a study guide covering all topics likely to appear on exams")
    response = agent.process_message("Create a study guide covering all topics likely to appear on exams")
    print(f"Agent: {response.message}")
    
    if response.execution_result:
        print(f"Steps completed: {response.execution_result.steps_completed}")
        print(f"Steps failed: {response.execution_result.steps_failed}")
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("AGENTIC SYSTEM TESTS")
    print("=" * 60)
    
    results = {}
    
    try:
        results['tool_registry'] = test_tool_registry()
    except Exception as e:
        print(f"Tool registry test failed: {e}")
        results['tool_registry'] = False
    
    try:
        results['basic_conversation'] = test_basic_conversation()
    except Exception as e:
        print(f"Basic conversation test failed: {e}")
        results['basic_conversation'] = False
    
    try:
        results['planning'] = test_planning()
    except Exception as e:
        print(f"Planning test failed: {e}")
        results['planning'] = False
    
    try:
        results['multi_document'] = test_multi_document_scenario()
    except Exception as e:
        print(f"Multi-document test failed: {e}")
        results['multi_document'] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    print("\nAll tests completed!")


if __name__ == "__main__":
    main()
