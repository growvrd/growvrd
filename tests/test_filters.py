import pytest
from core.filters import filter_by_location, filter_by_difficulty, filter_by_maintenance


def test_filter_by_location():
    """Test filtering plants by location"""
    test_plants = [
        {"id": "p001", "name": "Test Plant 1", "compatible_locations": "office,bedroom"},
        {"id": "p002", "name": "Test Plant 2", "compatible_locations": "kitchen,living_room"}
    ]

    # Test exact match
    filtered = filter_by_location(test_plants, "office")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "p001"

    # Test no match
    filtered = filter_by_location(test_plants, "bathroom")
    assert len(filtered) == 0

    # Test empty location
    filtered = filter_by_location(test_plants, "")
    assert len(filtered) == 2

    # Test None location
    filtered = filter_by_location(test_plants, None)
    assert len(filtered) == 2


def test_filter_by_difficulty():
    """Test filtering plants by difficulty level"""
    test_plants = [
        {"id": "p001", "name": "Easy Plant", "difficulty": 2},
        {"id": "p002", "name": "Medium Plant", "difficulty": 5},
        {"id": "p003", "name": "Hard Plant", "difficulty": 8}
    ]

    # Test beginner filter
    filtered = filter_by_difficulty(test_plants, "beginner")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "p001"

    # Test intermediate filter
    filtered = filter_by_difficulty(test_plants, "intermediate")
    assert len(filtered) == 2
    assert filtered[0]["id"] == "p001"
    assert filtered[1]["id"] == "p002"

    # Test advanced filter
    filtered = filter_by_difficulty(test_plants, "advanced")
    assert len(filtered) == 3