"""Foundation checks; integration checks run against Compose separately."""
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class FoundationTests(unittest.TestCase):
    def test_page_renders(self):
        from streamlit.testing.v1 import AppTest
        page = AppTest.from_file(str(ROOT / "dashboard/app.py")).run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(page.title[0].value, "Shopify Analytics POC — Environment Ready.")

    def test_database_probe_uses_authenticated_connection(self):
        from pipeline.healthcheck import check_database
        env = {"POSTGRES_HOST": "postgres", "POSTGRES_DB": "test", "POSTGRES_USER": "test", "DBT_ENV_SECRET_POSTGRES_PASSWORD": "unit-test-only"}
        with patch.dict("os.environ", env), patch("pipeline.healthcheck.psycopg.connect") as connect:
            connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (1,)
            check_database()
            self.assertEqual(connect.call_args.kwargs["connect_timeout"], 5)
            self.assertEqual(connect.call_args.kwargs["password"], env["DBT_ENV_SECRET_POSTGRES_PASSWORD"])

    def test_compose_security_boundaries(self):
        import yaml
        config = yaml.safe_load((ROOT / "compose.yaml").read_text())
        services = config["services"]
        self.assertEqual(set(services), {"postgres", "app", "streamlit"})
        for name, service in services.items():
            self.assertIn("healthcheck", service)
            if name != "streamlit":
                self.assertNotIn("ports", service)
        self.assertEqual(services["streamlit"]["ports"], ["127.0.0.1:8501:8501"])
        self.assertNotIn("environment", services["streamlit"])
        app_env = services["app"]["environment"]
        self.assertIn("SHOPIFY_CLIENT_SECRET", app_env)
        self.assertNotIn("SHOPIFY_CLIENT_SECRET", services["postgres"]["environment"])
        self.assertIn("postgres_data", config["volumes"])

if __name__ == "__main__":
    unittest.main()
