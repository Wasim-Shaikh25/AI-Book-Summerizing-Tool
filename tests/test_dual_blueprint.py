import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.semantic.models import SourceBlueprint, DerivedBlueprint, BlueprintNode
from src.core.gemini.blueprint_builder import BlueprintBuilder
import pydantic
import pytest

def test_source_blueprint_immutability():
    node = BlueprintNode(title="Chapter 1", level=1)
    sb = SourceBlueprint(
        book_id="test_book",
        hierarchy=[node],
        concepts=[{"concept_name": "Test"}]
    )
    
    with pytest.raises(pydantic.ValidationError) if hasattr(pydantic, 'ValidationError') else pytest.raises(TypeError):
        # In Pydantic v2, frozen=True raises ValidationError on assignment
        # In some cases it might be TypeError
        sb.book_id = "new_id"

def test_dual_blueprint_flow():
    builder = BlueprintBuilder()
    concepts = [
        {"concept_id": "id_a", "concept_name": "Concept A", "importance": "core", "confidence": 0.9, "description": "Desc A"},
        {"concept_id": "id_b", "concept_name": "Concept B", "importance": "supporting", "confidence": 0.8, "description": "Desc B"}
    ]
    
    original_structure = [
        {
            "title": "Chapter 1",
            "children": [
                {"title": "Concept A"},
                {"title": "Missing Concept"}
            ]
        }
    ]
    
    # 1. Test mapping logic (internal method)
    hierarchy = builder._analyze_and_map_structure(original_structure, concepts)
    
    assert len(hierarchy) == 1
    assert hierarchy[0].title == "Chapter 1"
    assert len(hierarchy[0].children) == 2
    
    # Concept A should be explained
    concept_a_node = hierarchy[0].children[0]
    assert concept_a_node.title == "Concept A"
    # Note: In the real builder, usage_type is determined by LLM or heuristics
    # In our manual test of the model structure:
    assert concept_a_node.original_structure_path == "Chapter 1 > Concept A"
    
    # Missing Concept should be referenced_only
    missing_node = hierarchy[0].children[1]
    assert missing_node.title == "Missing Concept"
    assert missing_node.usage_type == "referenced_only"
    assert missing_node.original_structure_path == "Chapter 1 > Missing Concept"

    # 2. Build SourceBlueprint
    sb = SourceBlueprint(
        book_id="book_123",
        hierarchy=hierarchy,
        concepts=concepts
    )
    
    # 3. Build DerivedBlueprint from Source
    db = builder.build_derived_blueprint(sb, authorial_intent="Focus on Concept A")
    
    assert db.book_id == sb.book_id
    assert db.source_blueprint_id == sb.book_id
    assert len(db.concepts) == len(sb.concepts)
    assert db.authorial_intent == "Focus on Concept A"

if __name__ == "__main__":
    # Manual run if pytest not available
    try:
        test_source_blueprint_immutability()
        print("Immutability test passed!")
        test_dual_blueprint_flow()
        print("Flow test passed!")
    except Exception as e:
        print(f"Test failed: {e}")
