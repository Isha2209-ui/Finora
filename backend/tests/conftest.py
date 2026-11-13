import pytest
from fastapi.testclient import TestClient

from app.main import app

DEMO = {"ABCDE1234F": "FINORA_USER_001", "PQRST5678K": "FINORA_USER_002", "LMNOP2345D": "FINORA_USER_003", "XYZAB9876C": "FINORA_USER_004"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def analyses(client):
    return {uid: client.get(f"/api/profiles/{uid}/analysis").json() for uid in DEMO.values()}
