import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


class TestApi(unittest.TestCase):
    def test_pricing_preview(self):
        r = client.post("/pricing/preview", json={"cost": 100.0, "competitor_price": 120.0})
        self.assertEqual(r.status_code, 200)
        self.assertIn("suggested_price", r.json())

    def test_pricing_run_and_approve(self):
        r = client.post("/pricing/run")
        self.assertEqual(r.status_code, 200)
        rid = r.json()["id"]
        r2 = client.post("/recommendations/" + rid + "/approve")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["status"], "approved")
