"""Simple test runner for orchestration layer tests.

Run this locally to verify the orchestration layer implementation:
    python run_orchestration_tests.py
"""

import subprocess
import sys


def run_tests():
    """Run all orchestration-related tests."""
    test_files = [
        "tests/unit/test_tool_registry.py",
        "tests/unit/test_tool_executor.py",
        "tests/unit/test_research_agent.py",
        "tests/unit/test_read_tools.py",
        "tests/unit/test_corpus_tools.py",
    ]

    print("=" * 60)
    print("Running Orchestration Layer Tests")
    print("=" * 60)

    all_passed = True
    for test_file in test_files:
        print(f"\nRunning: {test_file}")
        print("-" * 60)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-v"],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        if result.returncode != 0:
            all_passed = False
            print(f"❌ {test_file} FAILED")
        else:
            print(f"✅ {test_file} PASSED")

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests PASSED")
        return 0
    else:
        print("❌ Some tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
