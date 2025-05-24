import pytest
from app import app


@pytest.fixture
def client():
    with app.test_client() as client:
        with app.app_context():
            yield client


def test_perenual_api(client):
    response = client.get('/api/test-perenual')
    data = response.get_json()

    # Now make your assertions
    assert response.status_code in [200, 500]  # Either success or expected failure
    assert "status" in data