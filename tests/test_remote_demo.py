"""Deployment policy, real HTTP admission and Streamlit UI; no live Shopify calls."""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from dashboard import pipeline_client
from pipeline import api, run
from runtime_config import remote_demo_read_only
from test_dashboard import CATALOG, snapshot

TOKEN="independent-unit-test-trigger-"+"t"*40
ROOT=Path(__file__).resolve().parents[1]
IDLE={"current":None,"publication":None}


@contextmanager
def backend(value):
    with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":value,"PIPELINE_TRIGGER_TOKEN":TOKEN}):
        server=api.make_server(("127.0.0.1",0))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    def request(path="/runs",method="POST",token=TOKEN,body=b""):
        headers={"Authorization":"Bearer "+token} if token else {}
        req=Request(f"http://127.0.0.1:{server.server_port}"+path,method=method,
                    data=body if method=="POST" else None,headers=headers)
        try:
            with urlopen(req,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as exc:return exc.code,json.load(exc)
    try:
        yield request
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class SettingTests(unittest.TestCase):
    def test_unset_default_and_explicit_booleans(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(remote_demo_read_only())
        for value,expected in (("true",True),("false",False)):
            with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":value}):
                self.assertIs(remote_demo_read_only(),expected)

    def test_invalid_values_rejected_without_echoing_them(self):
        for value in ("", "TRUE", "False", "1", "0", "yes", " true", "false ", "unexpected-sensitive-value"):
            with self.subTest(value=value),patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":value}):
                with self.assertRaisesRegex(ValueError,"must be exactly") as error:remote_demo_read_only()
                if value:self.assertNotIn(value,str(error.exception))

    def test_invalid_backend_configuration_fails_before_binding(self):
        with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":"invalid"}),patch("pipeline.api.Server") as server:
            with self.assertRaises(ValueError):api.make_server()
        server.assert_not_called()


class RemoteInterfaceTests(unittest.TestCase):
    def test_valid_invalid_and_missing_tokens_cannot_start_runs(self):
        with backend("true") as request,patch("pipeline.api.start") as start,patch("pipeline.api.connect") as connect:
            for token in (TOKEN,"wrong",None):
                code,body=request(token=token)
                self.assertEqual(code,403)
                self.assertEqual(body,{"error":"Pipeline execution is disabled in read-only demo mode."})
                self.assertNotIn(TOKEN,json.dumps(body))
            # Body/query tricks cannot override the process-level policy either.
            self.assertEqual(request(body=b'{"REMOTE_DEMO_READ_ONLY":false}')[0],403)
            self.assertEqual(request(path="/runs?REMOTE_DEMO_READ_ONLY=false")[0],403)
            start.assert_not_called()
            connect.assert_not_called()  # No lock, audit row or worker admitted.

    def test_read_only_status_keeps_authentication_and_health_stays_available(self):
        with backend("true") as request,patch("pipeline.api.connect") as connect,patch("pipeline.api.status",return_value=IDLE) as status:
            for token in (None,"wrong"):
                self.assertEqual(request("/status","GET",token)[0],401)
            connect.assert_not_called()
            self.assertEqual(request("/status","GET"),(200,IDLE))
            status.assert_called_once()
            self.assertEqual(request("/health","GET",None),(200,{"status":"ok"}))

    def test_false_preserves_authentication_success_and_busy_responses(self):
        with backend("false") as request,patch("pipeline.api.start",return_value="safe-run-id") as start:
            self.assertEqual(request(token=None)[0],401)
            start.assert_not_called()
            self.assertEqual(request()[0],202)
            start.assert_called_once_with()
            start.return_value=None
            self.assertEqual(request()[0],409)

    def test_server_policy_does_not_change_until_container_recreation(self):
        with backend("true") as request,patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":"false"}),patch("pipeline.api.start") as start:
            self.assertEqual(request()[0],403)
            start.assert_not_called()

    def test_mismatched_ui_gets_useful_forbidden_message(self):
        forbidden=HTTPError("http://app:8080/runs",403,"Forbidden",{},io.BytesIO(b"sensitive-response"))
        opener=Mock()
        opener.open.side_effect=forbidden
        with patch.dict(os.environ,{"PIPELINE_TRIGGER_TOKEN":TOKEN}),patch("dashboard.pipeline_client.build_opener",return_value=opener):
            with self.assertRaises(pipeline_client.Unavailable) as error:pipeline_client.trigger()
        self.assertEqual(str(error.exception),"Pipeline execution is disabled in read-only demo mode.")


class RemotePageTests(unittest.TestCase):
    def test_reads_filters_and_charts_work_without_trigger_control(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":"true"}),patch("dashboard.pipeline_client.status",return_value=IDLE),patch("dashboard.pipeline_client.trigger") as trigger,patch("dashboard.data.catalog",return_value=CATALOG),patch("dashboard.data.load",return_value=snapshot()) as load:
            page=AppTest.from_file(str(ROOT/"dashboard/app.py")).run()
            self.assertFalse(page.exception)
            self.assertTrue(any(c.value=="Read-only demo" for c in page.caption))
            self.assertEqual(len(page.button),0)
            self.assertEqual(page.metric[3].value,"CAD 200.00")
            self.assertEqual(len(page.get("plotly_chart")),3)
            # Browser-controlled state cannot change the deployment setting.
            page.session_state["REMOTE_DEMO_READ_ONLY"]=False
            page.query_params["REMOTE_DEMO_READ_ONLY"]="false"
            page.selectbox[0].set_value("Synthetic Demo").run()
            self.assertFalse(page.exception)
            self.assertTrue(load.call_args.args[0].synthetic)
            page.selectbox[2].set_value("USD").run()
            self.assertEqual(load.call_args.args[0].currency,"USD")
            self.assertEqual(len(page.button),0)
            trigger.assert_not_called()

    def test_forged_button_event_cannot_enter_trigger_branch(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":"true"}),patch("dashboard.pipeline_client.status",return_value=IDLE),patch("dashboard.data.catalog",return_value=[]),patch("streamlit.button",return_value=True) as button,patch("dashboard.pipeline_client.trigger") as trigger:
            page=AppTest.from_file(str(ROOT/"dashboard/app.py")).run()
            self.assertFalse(page.exception)
            button.assert_not_called()
            trigger.assert_not_called()

    def test_unavailable_backend_keeps_read_only_notice_and_hides_button(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":"true"}),patch("dashboard.pipeline_client.status",side_effect=pipeline_client.Unavailable("Backend unavailable")),patch("dashboard.data.catalog",return_value=CATALOG),patch("dashboard.data.load",return_value=snapshot()):
            page=AppTest.from_file(str(ROOT/"dashboard/app.py")).run()
            self.assertFalse(page.exception)
            self.assertEqual(len(page.metric),4)
            self.assertEqual(len(page.button),0)
            self.assertTrue(any(c.value=="Read-only demo" for c in page.caption))

    def test_invalid_ui_configuration_fails_closed_and_preserves_reads(self):
        from streamlit.testing.v1 import AppTest
        with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":"invalid-sensitive-value"}),patch("dashboard.pipeline_client.trigger") as trigger,patch("dashboard.data.catalog",return_value=CATALOG),patch("dashboard.data.load",return_value=snapshot()):
            page=AppTest.from_file(str(ROOT/"dashboard/app.py")).run()
            self.assertFalse(page.exception)
            self.assertEqual(len(page.button),0)
            self.assertEqual(len(page.metric),4)
            self.assertIn("must be exactly",page.error[0].value)
            self.assertNotIn("invalid-sensitive-value",page.error[0].value)
            trigger.assert_not_called()


class OperatorTests(unittest.TestCase):
    def test_operator_cli_is_available_while_http_policy_is_read_only(self):
        connection=MagicMock()
        run_id=uuid4()
        with patch.dict(os.environ,{"REMOTE_DEMO_READ_ONLY":"true"}),patch("pipeline.run.connect",return_value=connection),patch("pipeline.run.initialize"),patch("pipeline.run.prepare",return_value=run_id),patch("pipeline.run.execute",return_value={"status":"succeeded"}) as execute,patch("builtins.print"):
            self.assertEqual(run.main(),0)
        execute.assert_called_once_with(connection.__enter__.return_value,run_id)
