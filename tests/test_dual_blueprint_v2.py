import sys
import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.semantic.models import SourceBlueprint, DerivedBlueprint, BlueprintNode, ExplanationDepth
from src.core.gemini.blueprint_builder import BlueprintBuilder

def test_derived_blueprint_rules():
    builder = BlueprintBuilder()
    
    # Setup a mock SourceBlueprint
    concepts = [
        {"concept_id": "id_1", "concept_name": "Topic 1", "description": "Detailed explanation 1", "usage_type": "explained"},
        {"concept_id": "id_2", "concept_name": "Topic 2", "description": "Detailed explanation 2", "usage_type": "explained"},
        {"concept_id": "id_3", "concept_name": "Topic 3", "description": "Passing reference", "usage_type": "referenced_only"}
    ]
    
    source_hierarchy = [
        BlueprintNode(
            title="Chapter 1",
            level=1,
            children=[
                BlueprintNode(title="Topic 1", level=2, concept_ids=["id_1"], usage_type="explained"),
                BlueprintNode(title="Topic 2", level=2, concept_ids=["id_2"], usage_type="explained"),
                BlueprintNode(title="Topic 3", level=2, concept_ids=["id_3"], usage_type="referenced_only")
            ]
        )
    ]
    
    sb = SourceBlueprint(
        book_id="test_book",
        hierarchy=source_hierarchy,
        concepts=concepts
    )
    
    print("Generating DerivedBlueprint...")
    # This will call the LLM. In a real test environment we might mock this, 
    # but for verification we'll see if it handles the response correctly.
    db = builder.build_derived_blueprint(sb, authorial_intent="Merge Topic 1 and 2 into 'Core Concepts'.")
    
    print(f"Derived Blueprint Title: {db.hierarchy[0].title}")
    for node in db.hierarchy[0].children:
        print(f"  Node: {node.title}, IDs: {node.concept_ids}")
        
    # Verification logic
    assert db.book_id == sb.book_id
    assert len(db.hierarchy) == len(sb.hierarchy) # No new levels or cross-chapter
    
    # Check mapping integrity
    for ch in db.hierarchy:
        for sec in ch.children:
            assert len(sec.concept_ids) > 0
            for cid in sec.concept_ids:
                # Ensure every ID exists in source concepts
                assert any(c["concept_id"] == cid for c in sb.concepts)

if __name__ == "__main__":
    try:
        test_derived_blueprint_rules()
        print("\nSUCCESS: DerivedBlueprint rules and mapping integrity verified.")
    except Exception as e:
        print(f"\nFAILURE: {e}")
        import traceback
        traceback.print_exc()
