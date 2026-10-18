"""Workflow/HTTP/UI checks. No live Shopify requests in this module."""
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from pipeline import api, run


class WorkflowTests(unittest.TestCase):
    def test_execution_order_and_success(self):
        events=[]
        conn=Mock()
        run_id=uuid4()
        with patch("pipeline.run.stage",side_effect=lambda c,r,n,s:events.append((n,s))),patch("pipeline.run.locking.release") as release:
            result=run.execute(conn,run_id,lambda c:events.append("extract"),
                               lambda:events.append("validate"),lambda c,r:events.append("publish"))
        self.assertEqual(result["status"],"succeeded")
        self.assertEqual(events,[("ingestion","running"),"extract",("ingestion","succeeded"),
                                 ("dbt","running"),"validate",("dbt","succeeded"),("publish","running"),"publish"])
        release.assert_called_once_with(conn)

    def test_each_stage_failure_stops_and_sanitizes(self):
        for failed in range(3):
            actions=[Mock(),Mock(),Mock()]
            actions[failed].side_effect=RuntimeError("secret-password customer@example.com")
            conn=Mock()
            with patch("pipeline.run.stage"),patch("pipeline.run.locking.release"):
                result=run.execute(conn,uuid4(),*actions)
            self.assertEqual(result["status"],"failed")
            self.assertNotIn("secret-password",json.dumps(result))
            self.assertNotIn("customer@",repr(conn.execute.call_args_list))
            conn.rollback.assert_called_once()
            for action in actions[failed+1:]:action.assert_not_called()

    def test_busy_does_not_create_audit(self):
        conn=Mock()
        with patch("pipeline.run.locking.acquire",return_value=False):
            self.assertIsNone(run.prepare(conn))
        conn.execute.assert_not_called()

    def test_dbt_is_fixed_no_shell_and_strips_shopify_secrets(self):
        completed=Mock(returncode=0)
        with patch("pipeline.run.subprocess.run",return_value=completed) as process,patch("pathlib.Path.read_text",return_value='{"results":[{"status":"pass"}]}'),patch.dict(os.environ,{"SHOPIFY_CLIENT_SECRET":"unit-secret","PIPELINE_TRIGGER_TOKEN":"unit-token"}):
            run.build_dbt()
        argv=process.call_args.args[0]
        self.assertEqual(argv[:3],["dbt","--warn-error","build"])
        self.assertFalse(process.call_args.kwargs["shell"])
        self.assertNotIn("SHOPIFY_CLIENT_SECRET",process.call_args.kwargs["env"])
        self.assertNotIn("PIPELINE_TRIGGER_TOKEN",process.call_args.kwargs["env"])

    def test_trigger_secret_independent_and_required(self):
        for token in ("short","replace-with-"+"x"*40,"x"*40):
            with patch.dict(os.environ,{"PIPELINE_TRIGGER_TOKEN":token,"DASHBOARD_DB_PASSWORD":"x"*40}):
                with self.assertRaises(ValueError):api.token_from_env()


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.token="unit-test-independent-"+"t"*40
        with patch.dict(os.environ,{"PIPELINE_TRIGGER_TOKEN":self.token}):
            self.server=api.make_server(("127.0.0.1",0))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url="http://127.0.0.1:"+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self,path,method="GET",token=None,body=None):
        req=Request(self.url+path,data=body,method=method,
                    headers={"Authorization":"Bearer "+token} if token else {})
        try:
            with urlopen(req,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as exc:return exc.code,json.load(exc)

    def test_authentication_required_for_trigger_and_status(self):
        with patch("pipeline.api.start") as start:
            for token in (None,"incorrect"):
                self.assertEqual(self.request("/runs","POST",token,b"")[0],401)
                self.assertEqual(self.request("/status",token=token)[0],401)
            start.assert_not_called()

    def test_no_parameters_or_arbitrary_operations(self):
        with patch("pipeline.api.start") as start:
            self.assertEqual(self.request("/runs","POST",self.token,b'{"command":"whoami"}')[0],400)
            self.assertEqual(self.request("/runs?sql=select1","POST",self.token,b"")[0],404)
            self.assertEqual(self.request("/shell","POST",self.token,b"")[0],404)
            start.assert_not_called()

    def test_accept_busy_and_sanitized_backend_failure(self):
        with patch("pipeline.api.start",return_value="safe-uuid"):
            self.assertEqual(self.request("/runs","POST",self.token,b"")[0],202)
        with patch("pipeline.api.start",return_value=None):
            code,body=self.request("/runs","POST",self.token,b"")
            self.assertEqual((code,body["status"]),(409,"already_running"))
        with patch("pipeline.api.start",side_effect=RuntimeError(self.token)):
            code,body=self.request("/runs","POST",self.token,b"")
            self.assertEqual(code,503)
            self.assertNotIn(self.token,json.dumps(body))


class ControlsTests(unittest.TestCase):
    def render(self,state):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"dashboard/app.py"))
        with patch("dashboard.pipeline_client.status",return_value=state),patch("dashboard.data.catalog",return_value=[]):
            return app.run()

    def test_idle_running_succeeded_failed_labels_and_button(self):
        for status,label in ((None,"Idle"),("running","Running"),("succeeded","Succeeded"),("failed","Failed")):
            current={"status":status,"id":"safe-uuid","stage":"dbt","error":"Validation failed"} if status else None
            page=self.render({"current":current,"publication":None})
            self.assertFalse(page.exception)
            self.assertTrue(any(label in header.value for header in page.subheader))
            self.assertEqual(page.button[0].disabled,status=="running")
            if status=="failed":self.assertTrue(page.error)

    def test_click_uses_only_trigger_interface(self):
        with patch("dashboard.pipeline_client.status",return_value={"current":None,"publication":None}),patch("dashboard.data.catalog",return_value=[]),patch("dashboard.pipeline_client.trigger",return_value={"status":"running"}) as trigger:
            page=self.render({"current":None,"publication":None})
            page.button[0].click().run()
            self.assertFalse(page.exception)
            trigger.assert_called_once_with()

    def test_failed_run_does_not_refresh_and_new_publication_does(self):
        from streamlit.testing.v1 import AppTest
        page=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"dashboard/app.py"))
        state={"current":None,"publication":{"run_id":"old","published_at":"old-date"}}
        with patch("dashboard.pipeline_client.status",side_effect=lambda:state),patch("dashboard.data.catalog",return_value=[]),patch("streamlit.cache_data.clear") as clear:
            page.run()
            state["current"]={"status":"failed","id":"failed","stage":"dbt","error":"Validation failed"}
            page.run()
            clear.assert_not_called()
            state["publication"]={"run_id":"new","published_at":"new-date"}
            page.run()
            clear.assert_called_once()
            self.assertFalse(page.exception)
