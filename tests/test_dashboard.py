"""Dashboard queries, presentation and safe failure handling using isolated mocks."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import Mock, MagicMock, patch

from dashboard import data, charts

DAY=date(2026,10,16)
CATALOG=[{"store_domain":"demo.myshopify.com","is_synthetic":False,"currency_code":"CAD","first_date":DAY,"last_date":DAY},
         {"store_domain":"fixture.invalid","is_synthetic":True,"currency_code":"CAD","first_date":date(2026,10,1),"last_date":date(2026,10,6)},
         {"store_domain":"fixture.invalid","is_synthetic":True,"currency_code":"USD","first_date":date(2026,10,2),"last_date":date(2026,10,2)}]


def snapshot(status="ready", net=Decimal("200")):
    kpis={"day_count":1,"gross_sales":Decimal("200"),"discounts":Decimal("0"),"returns_amount":Decimal("0"),"net_sales":net}
    daily=[{"reporting_date":DAY,**{k:kpis[k] for k in data.METRICS},"unsupported_event_count":0}]
    return {"status":status,"kpis":kpis,"daily":daily,"products":[{"product_key":"p1","title":"Example","net_sales":net}],
            "issue_count":0,"last_successful_ingestion_at":datetime(2026,10,17,tzinfo=timezone.utc)}


class QueryTests(unittest.TestCase):
    def factory(self, daily=None,kpis=None,products=None,issues=0):
        result=snapshot()
        conn=Mock()
        conn.execute.side_effect=[Mock(fetchall=Mock(return_value=result["daily"] if daily is None else daily)),
                                  Mock(fetchone=Mock(return_value=result["kpis"] if kpis is None else kpis)),
                                  Mock(fetchall=Mock(return_value=result["products"] if products is None else products)),
                                  Mock(fetchone=Mock(return_value={"issue_count":issues})),
                                  Mock(fetchone=Mock(return_value=None))]
        factory=MagicMock()
        factory.return_value.__enter__.return_value=conn
        return factory,conn

    def test_filters_bound_as_parameters_for_every_query(self):
        filters=data.Filters(True,"fixture.invalid' OR true --","CAD",DAY,DAY)
        factory,conn=self.factory()
        self.assertEqual(data.load(filters,factory)["status"],"ready")
        for call in conn.execute.call_args_list[:4]:
            self.assertEqual(call.args[1],filters.params)
            self.assertNotIn(filters.store,call.args[0])
        self.assertEqual(conn.execute.call_args_list[4].args[1],(True,filters.store))
        self.assertIn("is_test=false",data.PRODUCTS_SQL)

    def test_empty_selection_preserves_nulls(self):
        factory,_=self.factory(daily=[],products=[],kpis={"day_count":0,**dict.fromkeys(data.METRICS)})
        result=data.load(data.Filters(False,"demo.myshopify.com","CAD",DAY,DAY),factory)
        self.assertEqual(result["status"],"empty")
        self.assertIsNone(result["kpis"]["net_sales"])
        self.assertIsNone(result["last_successful_ingestion_at"])

    def test_any_unsupported_record_withholds_all_figures(self):
        for issues in (0,1):
            daily=snapshot()["daily"]
            if not issues:daily[0]["net_sales"]=None
            factory,_=self.factory(daily=daily,issues=issues)
            result=data.load(data.Filters(False,"demo.myshopify.com","CAD",DAY,DAY),factory)
            self.assertEqual(result["status"],"unsupported")
            self.assertTrue(all(result["kpis"][key] is None for key in data.METRICS))
            self.assertEqual(result["products"],[])
            self.assertEqual(result["daily"],[])

    def test_database_errors_do_not_expose_exception(self):
        factory=Mock(side_effect=RuntimeError("secret-password connection-string"))
        for call in (lambda:data.catalog(factory),lambda:data.load(data.Filters(False,"store","CAD",DAY,DAY),factory)):
            with self.assertRaises(data.DashboardUnavailable) as caught:call()
            self.assertNotIn("secret-password",str(caught.exception))

    def test_invalid_range_rejected(self):
        with self.assertRaises(ValueError):data.Filters(False,"store","CAD",date(2026,10,2),date(2026,10,1))

    def test_currency_display_preserves_database_precision(self):
        from dashboard.app import amount
        self.assertEqual(amount(Decimal("1.234"),"TND"),"TND 1.234")
        self.assertEqual(amount(Decimal("200"),"CAD"),"CAD 200.00")
        self.assertEqual(amount(None,"CAD"),"—")

    def test_negative_return_chart_and_distinct_product_labels(self):
        row={"reporting_date":DAY,"gross_sales":Decimal(0),"net_sales":Decimal(-90),"returns_amount":Decimal(90)}
        self.assertEqual(list(charts.daily_trend([row],"CAD").data[1].y),[-90])
        self.assertEqual(list(charts.returns_trend([row],"CAD").data[0].y),[90])
        products=[{"product_key":"a","title":"Same title","net_sales":Decimal(5)},
                  {"product_key":"b","title":"Same title","net_sales":Decimal(-2)}]
        self.assertEqual(list(charts.top_products(products,"CAD").data[0].y),["a","b"])


class PageTests(unittest.TestCase):
    def setUp(self):
        self.backend=patch("dashboard.pipeline_client.status",return_value={"current":None,"publication":None})
        self.backend.start()
        self.addCleanup(self.backend.stop)

    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/"dashboard/app.py"))

    def test_default_live_and_all_charts_render(self):
        with patch("dashboard.data.catalog",return_value=CATALOG),patch("dashboard.data.load",return_value=snapshot()) as load:
            app=self.app().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.selectbox[0].value,"Live Shopify")
            self.assertEqual(len(app.metric),4)
            self.assertEqual(app.metric[3].value,"CAD 200.00")
            self.assertEqual(len(app.get("plotly_chart")),3)
            self.assertFalse(app.button[0].disabled)
            self.assertFalse(load.call_args.args[0].synthetic)

    def test_dataset_currency_and_dates_apply_together(self):
        with patch("dashboard.data.catalog",return_value=CATALOG),patch("dashboard.data.load",return_value=snapshot()) as load:
            app=self.app().run()
            app.selectbox[0].set_value("Synthetic Demo").run()
            self.assertTrue(load.call_args.args[0].synthetic)
            self.assertEqual(load.call_args.args[0].store,"fixture.invalid")
            app.selectbox[2].set_value("USD").run()
            self.assertEqual(load.call_args.args[0].currency,"USD")
            self.assertEqual(load.call_args.args[0].start,date(2026,10,2))

    def test_empty_catalog_and_safe_unavailable_state(self):
        with patch("dashboard.data.catalog",return_value=[]):
            app=self.app().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.metric),0)
        with patch("dashboard.data.catalog",side_effect=data.DashboardUnavailable("Analytics is not ready")):
            app=self.app().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.warning),1)

    def test_unsupported_selection_does_not_draw_partial_charts(self):
        blocked=snapshot("unsupported")
        blocked["kpis"].update(dict.fromkeys(data.METRICS))
        with patch("dashboard.data.catalog",return_value=CATALOG),patch("dashboard.data.load",return_value=blocked):
            app=self.app().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.error),1)
            self.assertEqual(len(app.get("plotly_chart")),0)
            self.assertTrue(all(m.value=="—" for m in app.metric))
