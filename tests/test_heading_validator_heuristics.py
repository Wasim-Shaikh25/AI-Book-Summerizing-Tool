from src.structure.heading_heuristics import should_force_invalid_enumerated_list_item


def test_should_not_block_section_number_like_1_2():
    assert (
        should_force_invalid_enumerated_list_item(
            "1.2 Distinction from Crime, Breach of Contract etc., who may sue"
        )
        is False
    )


def test_should_block_long_single_level_enumeration_like_deterrence():
    assert (
        should_force_invalid_enumerated_list_item(
            "3. Deterrence: Deterrence theory about law says that the threat or the fear imposed by law will"
        )
        is True
    )
