"""Check deployed mode, real HTTP policy and published reads; never triggers a run.

Get-Content tests/e2e_remote_demo.py -Raw | docker compose exec -T streamlit python -
Run once after recreating both containers in each deployment mode.
"""
from datetime import date
from decimal import Decimal
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from streamlit.testing.v1 import AppTest
from dashboard import data, pipeline_client
from runtime_config import remote_demo_read_only


def request(path,method="GET",token=None,body=b""):
    headers={"Authorization":"Bearer "+token} if token else {}
    req=Request("http://app:8080"+path,method=method,headers=headers,
                data=body if method=="POST" else None)
    try:
        with urlopen(req,timeout=5) as response:return response.status,json.load(response)
    except HTTPError as exc:return exc.code,json.load(exc)


read_only=remote_demo_read_only()
token=os.environ["PIPELINE_TRIGGER_TOKEN"]
assert request("/health")== (200,{"status":"ok"})
assert request("/status")[0]==401
assert request("/status",token="wrong")[0]==401
assert request("/status",token=token)[0]==200
before=pipeline_client.status()
if read_only:
    for supplied in (None,"wrong",token):
        code,body=request("/runs","POST",supplied)
        assert code==403
        assert "read-only demo" in body["error"]
    assert request("/runs","POST",token,b'{"REMOTE_DEMO_READ_ONLY":false}')[0]==403
    assert request("/runs?REMOTE_DEMO_READ_ONLY=false","POST",token)[0]==403
else:
    # These requests prove local auth/body validation still works without
    # actually admitting a Shopify pipeline run in this read-only check.
    assert request("/runs","POST")[0]==401
    assert request("/runs","POST",token,b'{"command":"not-accepted"}')[0]==400
assert pipeline_client.status()==before

live=data.load(data.Filters(False,"demo-analytics-poc.myshopify.com","CAD",date(2026,10,1),date(2026,10,31)))
assert live["status"]=="ready"
assert live["kpis"]["net_sales"]==Decimal(200)
page=AppTest.from_file("/app/dashboard/app.py",default_timeout=15).run()
assert not page.exception
assert page.metric[3].value=="CAD 200.00"
assert len(page.get("plotly_chart"))==3
if read_only:
    assert len(page.button)==0
    assert any(c.value=="Read-only demo" for c in page.caption)
    page.session_state["REMOTE_DEMO_READ_ONLY"]=False
    page.query_params["REMOTE_DEMO_READ_ONLY"]="false"
else:
    assert len(page.button)==1
    assert not page.button[0].disabled
page.selectbox[0].set_value("Synthetic Demo").run()
assert not page.exception
assert [m.value for m in page.metric]==["CAD 340.00","CAD 25.00","CAD 180.00","CAD 135.00"]
page.date_input[0].set_value((date(2026,10,4),date(2026,10,4))).run()
assert not page.exception
assert page.metric[3].value=="CAD -90.00"
page.selectbox[2].set_value("USD").run()
assert not page.exception
assert page.metric[3].value=="USD 7.00"
if read_only:assert len(page.button)==0
print(json.dumps({"read_only":read_only,"trigger":"403 (all tokens)" if read_only else "existing auth/body validation",
                  "status":"authenticated", "dashboard_reads":"live CAD200; synthetic CAD340/25/180/135; later CAD-90; USD7",
                  "browser_policy_override":"blocked" if read_only else "local controls available",
                  "pipeline_status_unchanged":True}))
