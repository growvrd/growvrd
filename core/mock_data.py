"""
Simplified Mock Data for GrowVRD Development

This provides a reliable fallback when other data sources aren't available.
Focus on core plants that work well for testing the recommendation engine.
"""

def get_mock_plants():
    """Return a curated list of plants perfect for testing recommendations"""
    return [
        {
            "id": "p001",
            "name": "snake_plant",
            "scientific_name": "dracaena_trifasciata",
            "natural_sunlight_needs": "low_indirect",
            "led_light_requirements": "low",
            "water_frequency_days": 14,
            "humidity_preference": "low",
            "difficulty": 1,
            "maintenance": "low",
            "indoor_compatible": True,
            "description": "Hardy, air-purifying plant with vertical leaves. Perfect for beginners and tolerates neglect.",
            "compatible_locations": ["office", "bedroom", "living_room"],
            "functions": ["air_purification", "decoration", "night_oxygen"],
            "toxic_to_pets": True,
            "image_url": "https://example.com/plants/snake_plant.jpg"
        },
        {
            "id": "p002",
            "name": "pothos",
            "scientific_name": "epipremnum_aureum",
            "natural_sunlight_needs": "indirect",
            "led_light_requirements": "medium",
            "water_frequency_days": 7,
            "humidity_preference": "moderate",
            "difficulty": 2,
            "maintenance": "low",
            "indoor_compatible": True,
            "description": "Trailing vine with heart-shaped leaves. Adapts to various light conditions and very forgiving.",
            "compatible_locations": ["living_room", "bedroom", "office"],
            "functions": ["air_purification", "decoration"],
            "toxic_to_pets": True,
            "image_url": "https://example.com/plants/pothos.jpg"
        },
        {
            "id": "p003",
            "name": "peace_lily",
            "scientific_name": "spathiphyllum",
            "natural_sunlight_needs": "low_indirect",
            "led_light_requirements": "medium",
            "water_frequency_days": 7,
            "humidity_preference": "high",
            "difficulty": 4,
            "maintenance": "moderate",
            "indoor_compatible": True,
            "description": "Elegant flowering plant known for air-purifying qualities. Tells you when it needs water by drooping.",
            "compatible_locations": ["bathroom", "office", "bedroom"],
            "functions": ["air_purification", "decoration"],
            "toxic_to_pets": True,
            "image_url": "https://example.com/plants/peace_lily.jpg"
        },
        {
            "id": "p004",
            "name": "spider_plant",
            "scientific_name": "chlorophytum_comosum",
            "natural_sunlight_needs": "indirect",
            "led_light_requirements": "medium",
            "water_frequency_days": 7,
            "humidity_preference": "moderate",
            "difficulty": 2,
            "maintenance": "low",
            "indoor_compatible": True,
            "description": "Fast-growing plant that produces baby plants. Excellent air purifier and very forgiving for beginners.",
            "compatible_locations": ["living_room", "bedroom", "office"],
            "functions": ["air_purification", "decoration"],
            "toxic_to_pets": False,
            "image_url": "https://example.com/plants/spider_plant.jpg"
        },
        {
            "id": "p005",
            "name": "aloe_vera",
            "scientific_name": "aloe_barbadensis_miller",
            "natural_sunlight_needs": "bright_indirect",
            "led_light_requirements": "medium",
            "water_frequency_days": 21,
            "humidity_preference": "low",
            "difficulty": 3,
            "maintenance": "low",
            "indoor_compatible": True,
            "description": "Medicinal succulent with healing gel in leaves. Thrives in dry conditions and bright light.",
            "compatible_locations": ["kitchen", "bathroom", "living_room"],
            "functions": ["skin_care", "air_purification", "medicinal"],
            "toxic_to_pets": True,
            "image_url": "https://example.com/plants/aloe.jpg"
        },
        {
            "id": "p006",
            "name": "basil",
            "scientific_name": "ocimum_basilicum",
            "natural_sunlight_needs": "direct",
            "led_light_requirements": "high",
            "water_frequency_days": 3,
            "humidity_preference": "moderate",
            "difficulty": 4,
            "maintenance": "moderate",
            "indoor_compatible": True,
            "description": "Aromatic culinary herb with bright green leaves. Perfect for cooking and adds fresh flavor to meals.",
            "compatible_locations": ["kitchen"],
            "functions": ["culinary", "aromatherapy"],
            "toxic_to_pets": False,
            "image_url": "https://example.com/plants/basil.jpg"
        },
        {
            "id": "p007",
            "name": "mint",
            "scientific_name": "mentha_spicata",
            "natural_sunlight_needs": "partial_shade",
            "led_light_requirements": "medium",
            "water_frequency_days": 3,
            "humidity_preference": "high",
            "difficulty": 3,
            "maintenance": "moderate",
            "indoor_compatible": True,
            "description": "Vigorous herb perfect for teas and cooking. Grows quickly and needs regular watering.",
            "compatible_locations": ["kitchen"],
            "functions": ["culinary", "tea", "aromatherapy"],
            "toxic_to_pets": False,
            "image_url": "https://example.com/plants/mint.jpg"
        },
        {
            "id": "p008",
            "name": "zz_plant",
            "scientific_name": "zamioculcas_zamiifolia",
            "natural_sunlight_needs": "low_indirect",
            "led_light_requirements": "low",
            "water_frequency_days": 14,
            "humidity_preference": "low",
            "difficulty": 1,
            "maintenance": "low",
            "indoor_compatible": True,
            "description": "Nearly indestructible plant with glossy leaves. Perfect for offices and low-light areas.",
            "compatible_locations": ["office", "bedroom", "living_room"],
            "functions": ["air_purification", "decoration"],
            "toxic_to_pets": True,
            "image_url": "https://example.com/plants/zz_plant.jpg"
        }
    ]

def get_mock_products():
    """Return basic product data for testing"""
    return [
        {
            "id": "pr001",
            "name": "ceramic_pot",
            "category": "pot",
            "price": 19.99,
            "description": "Stylish ceramic pot with drainage hole",
            "compatible_locations": ["kitchen", "living_room", "bathroom"],
            "image_url": "https://example.com/products/ceramic_pot.jpg"
        },
        {
            "id": "pr002",
            "name": "potting_soil",
            "category": "soil",
            "price": 14.99,
            "description": "Premium potting mix for indoor plants",
            "compatible_locations": ["all"],
            "image_url": "https://example.com/products/soil.jpg"
        },
        {
            "id": "pr003",
            "name": "led_grow_light",
            "category": "grow_light",
            "price": 29.99,
            "description": "Full spectrum LED grow light with timer",
            "compatible_locations": ["all"],
            "image_url": "https://example.com/products/grow_light.jpg"
        }
    ]

def get_mock_kits():
    """Return basic kit data for testing"""
    return [
        {
            "id": "k001",
            "name": "beginner_office_kit",
            "locations": ["office"],
            "difficulty": "beginner",
            "plant_ids": ["p001", "p008"],
            "price": 45.00,
            "description": "Perfect starter kit for office spaces with low light",
            "image_url": "https://example.com/kits/office.jpg"
        },
        {
            "id": "k002",
            "name": "kitchen_herb_kit",
            "locations": ["kitchen"],
            "difficulty": "beginner",
            "plant_ids": ["p006", "p007"],
            "price": 35.00,
            "description": "Fresh herbs for cooking, perfect for kitchen windowsills",
            "image_url": "https://example.com/kits/herbs.jpg"
        }
    ]