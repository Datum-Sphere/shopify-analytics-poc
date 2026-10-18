"""Plot existing dbt metrics; floats are used only for chart serialization."""
import plotly.graph_objects as go

TEAL="#0F766E"
BLUE="#2563EB"
CORAL="#D16A52"


def style(figure,currency):
    figure.update_layout(template="plotly_white",height=350,margin=dict(l=10,r=20,t=30,b=20),
                         font=dict(family="Arial",color="#334155"),paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor="rgba(0,0,0,0)",legend=dict(orientation="h",y=1.12,x=0),
                         hovermode="x unified")
    figure.update_yaxes(title_text=currency,gridcolor="#E9EEF3",zeroline=True,zerolinecolor="#94A3B8")
    figure.update_xaxes(showgrid=False,title_text=None)
    return figure


def daily_trend(rows,currency):
    figure=go.Figure()
    for field,label,color in (("gross_sales","Gross sales",BLUE),("net_sales","Net sales",TEAL)):
        figure.add_trace(go.Scatter(x=[r["reporting_date"] for r in rows],y=[float(r[field]) for r in rows],
                                   name=label,mode="lines+markers",line=dict(color=color,width=3),
                                   marker=dict(size=7),connectgaps=False,hovertemplate="%{y:,.2f}<extra>"+label+"</extra>"))
    return style(figure,currency)


def returns_trend(rows,currency):
    figure=go.Figure(go.Bar(x=[r["reporting_date"] for r in rows],y=[float(r["returns_amount"]) for r in rows],
                           name="Merchandise reversals",marker_color=CORAL,hovertemplate="%{y:,.2f}<extra>Returns</extra>"))
    return style(figure,currency)


def top_products(rows,currency):
    rows=rows[:10]
    figure=go.Figure(go.Bar(x=[float(r["net_sales"]) for r in rows],y=[r["product_key"] for r in rows],
                           customdata=[r["title"] for r in rows],orientation="h",marker_color=TEAL,
                           hovertemplate="%{customdata}<br>%{x:,.2f}<extra>Net sales</extra>"))
    style(figure,currency)
    figure.update_layout(height=max(300,len(rows)*38),hovermode="closest")
    figure.update_yaxes(tickvals=[r["product_key"] for r in rows],ticktext=[r["title"] for r in rows],
                       autorange="reversed",title_text=None,showgrid=False)
    figure.update_xaxes(title_text="Net merchandise sales ("+currency+")",showgrid=True,gridcolor="#E9EEF3")
    return figure
