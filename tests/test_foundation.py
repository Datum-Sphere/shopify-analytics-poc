"""Foundation checks; integration checks run against Compose separately."""
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class FoundationTests(unittest.TestCase):
    def test_page_renders(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict("os.environ",{"REMOTE_DEMO_READ_ONLY":"false"}), patch("dashboard.data.catalog", return_value=[]), patch("dashboard.pipeline_client.status",return_value={"current":None,"publication":None}):
            page = AppTest.from_file(str(ROOT / "dashboard/app.py")).run()
        self.assertEqual(len(page.exception), 0)
        self.assertEqual(page.title[0].value, "Shopify Sales Analytics")
        self.assertFalse(page.button[0].disabled)

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
            if name == "app":
                self.assertNotIn("ports", service)
        self.assertEqual(services["postgres"]["ports"], ["127.0.0.1:5432:5432"])
        self.assertEqual(services["streamlit"]["ports"], ["127.0.0.1:8501:8501"])
        dashboard_env=services["streamlit"]["environment"]
        self.assertEqual(set(dashboard_env), {"DASHBOARD_DB_HOST","DASHBOARD_DB_PORT","DASHBOARD_DB_NAME","DASHBOARD_DB_PASSWORD","PIPELINE_API_URL","PIPELINE_TRIGGER_TOKEN","REMOTE_DEMO_READ_ONLY"})
        self.assertNotEqual(dashboard_env["DASHBOARD_DB_PASSWORD"], services["app"]["environment"]["DBT_ENV_SECRET_POSTGRES_PASSWORD"])
        app_env = services["app"]["environment"]
        self.assertIn("SHOPIFY_CLIENT_SECRET", app_env)
        self.assertEqual(dashboard_env["PIPELINE_TRIGGER_TOKEN"],app_env["PIPELINE_TRIGGER_TOKEN"])
        self.assertEqual(dashboard_env["REMOTE_DEMO_READ_ONLY"],"${REMOTE_DEMO_READ_ONLY-false}")
        self.assertEqual(dashboard_env["REMOTE_DEMO_READ_ONLY"],app_env["REMOTE_DEMO_READ_ONLY"])
        self.assertNotIn("REMOTE_DEMO_READ_ONLY",services["postgres"]["environment"])
        self.assertNotIn("PIPELINE_TRIGGER_TOKEN",services["postgres"]["environment"])
        self.assertNotIn("SHOPIFY_CLIENT_SECRET", services["postgres"]["environment"])
        self.assertIn("postgres_data", config["volumes"])

if __name__ == "__main__":
    unittest.main()
