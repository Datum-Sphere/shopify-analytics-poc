"""Opt-in LIVE Shopify workflow check, executed inside the Streamlit image.

PowerShell: Get-Content tests/e2e_pipeline.py -Raw | docker compose exec -T streamlit python -
Runs two read-only Shopify ingestions; never mutates the Shopify store.
"""
from datetime import date
from decimal import Decimal
import json
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from streamlit.testing.v1 import AppTest
from dashboard import data, pipeline_client


def metrics():
    live=data.load(data.Filters(False,"demo-analytics-poc.myshopify.com","CAD",date(2026,10,1),date(2026,10,31)))
    fixture=data.load(data.Filters(True,"financial-fixtures.invalid","CAD",date(2026,10,1),date(2026,10,6)))
    assert live["status"]==fixture["status"]=="ready"
    assert [live["kpis"][k] for k in data.METRICS]==[Decimal(200),Decimal(0),Decimal(0),Decimal(200)]
    assert [fixture["kpis"][k] for k in data.METRICS]==[Decimal(340),Decimal(25),Decimal(180),Decimal(135)]
    negative=data.load(data.Filters(True,"financial-fixtures.invalid","CAD",date(2026,10,4),date(2026,10,4)))
    assert negative["kpis"]["net_sales"]==Decimal(-90)
    return {"live":[str(live["kpis"][k]) for k in data.METRICS],
            "synthetic":[str(fixture["kpis"][k]) for k in data.METRICS]}


for method,path in (("POST","/runs"),("GET","/status")):
    try:
        urlopen(Request("http://app:8080"+path,method=method,data=b"" if method=="POST" else None),timeout=5)
        raise AssertionError("Unauthenticated operation was accepted")
    except HTTPError as exc:
        assert exc.code==401

before=metrics()
page=AppTest.from_file("/app/dashboard/app.py",default_timeout=15).run()
assert not page.exception
assert page.metric[3].value=="CAD 200.00"
run_ids=[]
expect_failure="--expect-failure" in sys.argv
for _ in range(1 if expect_failure else 2):
    old=pipeline_client.status()["publication"]["run_id"]
    assert not page.button[0].disabled
    page.button[0].click().run()
    assert not page.exception
    # The actual button calls the real internal backend. A simultaneous request
    # must be rejected before any second worker is admitted.
    assert pipeline_client.trigger()["status"]=="already_running"
    state=pipeline_client.status()
    assert state["current"]["status"]=="running"
    assert page.button[0].disabled
    new_id=state["current"]["id"]
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=pipeline_client.status()
        if state["current"]["status"]!="running":break
        time.sleep(1)
    assert state["current"]["id"]==new_id
    assert state["current"]["status"]==("failed" if expect_failure else "succeeded"),state["current"].get("error")
    if expect_failure:
        assert state["current"]["stage"]=="dbt"
        assert state["publication"]["run_id"]==old
    else:
        assert state["publication"]["run_id"]==new_id!=old
    run_ids.append(new_id)
    page.run()
    assert not page.exception
    assert page.metric[3].value=="CAD 200.00"
    assert any(("Failed" if expect_failure else "Succeeded") in x.value for x in page.subheader)
    assert page.session_state["publication_generation"]==(old if expect_failure else new_id)
    if expect_failure:
        assert page.error
    assert metrics()==before
page.selectbox[0].set_value("Synthetic Demo").run()
assert not page.exception
assert [m.value for m in page.metric]==["CAD 340.00","CAD 25.00","CAD 180.00","CAD 135.00"]
print(json.dumps({"live_button_runs":run_ids,"expected_failure":expect_failure,"metrics":before,"unauthorized":"401", "overlap":"rejected", "render":"passed"}))
