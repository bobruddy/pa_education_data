"""County and LEA sunburst of expense per enrolled student."""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, dcc, html

from pa_edu.chart import (
    MEASURE_PER_PUPIL,
    MEASURE_TOTAL,
    build_sunburst,
    counties,
    expense_frame,
    leas,
    selection_summary,
    tuition_years,
    years,
)

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server


def _year_label(year: int) -> str:
    return f"{year}-{str(year + 1)[-2:]}"


def _default_year(available_years: list[int]) -> int:
    published = [year for year in available_years if year in set(tuition_years())]
    return published[-1] if published else available_years[-1]


def _layout() -> html.Div:
    available_years = years()
    available_counties = counties()
    default_year = _default_year(available_years)
    default_county = "Chester" if "Chester" in available_counties else available_counties[0]
    default_leas = leas(default_county, default_year)
    default_frame = expense_frame(default_county, default_leas, default_year)
    return dbc.Container(
        [
            html.H1("PA school spending", className="mt-3"),
            html.P(
                "General Fund Budget amounts. Per pupil removes tuition paid to brick-and-mortar "
                "and cyber charters, including special-education charter tuition, because those "
                "students are in the charter's enrollment. Tuition for approved private schools "
                "and PRRIs stays in: those students remain in the district count."
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("View"),
                            dcc.RadioItems(
                                id="measure",
                                options=[
                                    {"label": "All expenses", "value": MEASURE_TOTAL},
                                    {"label": "Per pupil", "value": MEASURE_PER_PUPIL},
                                ],
                                value=MEASURE_PER_PUPIL,
                                inline=True,
                                inputClassName="me-1",
                                labelClassName="me-3",
                            ),
                        ],
                        md=12,
                    ),
                ],
                className="mb-2",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("School year"),
                            dcc.Dropdown(
                                id="year-dropdown",
                                clearable=False,
                                value=default_year,
                                options=[{"label": _year_label(year), "value": year} for year in available_years],
                            ),
                        ],
                        md=3,
                    ),
                    dbc.Col(
                        [
                            html.Label("County"),
                            dcc.Dropdown(
                                id="county-dropdown",
                                clearable=False,
                                value=default_county,
                                options=available_counties,
                            ),
                        ],
                        md=3,
                    ),
                    dbc.Col(
                        [
                            html.Label("LEA"),
                            dcc.Dropdown(
                                id="lea-dropdown",
                                clearable=True,
                                multi=True,
                                value=default_leas,
                                options=default_leas,
                            ),
                        ],
                        md=6,
                    ),
                ],
                className="g-3",
            ),
            html.Div(
                id="summary",
                className="mt-3",
                children=_summary_view(selection_summary(default_frame, MEASURE_PER_PUPIL, default_year)),
            ),
            dcc.Graph(
                id="sun-graph",
                figure=build_sunburst(default_county, default_leas, default_year, MEASURE_PER_PUPIL),
            ),
        ],
        fluid=True,
        className="pb-4",
    )


@app.callback(
    Output("lea-dropdown", "options"),
    Output("lea-dropdown", "value"),
    Input("county-dropdown", "value"),
    Input("year-dropdown", "value"),
)
def update_lea_dropdown(county: str, school_year: int):
    names = leas(county, int(school_year))
    return names, names


@app.callback(
    Output("sun-graph", "figure"),
    Output("summary", "children"),
    Input("lea-dropdown", "value"),
    Input("measure", "value"),
    Input("year-dropdown", "value"),
    State("county-dropdown", "value"),
)
def update_sun_graph(lea_names, measure: str, school_year: int, county: str):
    selected = lea_names or []
    school_year = int(school_year)
    frame = expense_frame(county, selected, school_year)
    return (
        build_sunburst(county, selected, school_year, measure),
        _summary_view(selection_summary(frame, measure, school_year)),
    )


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _summary_view(summary: dict) -> html.Div:
    if summary.get("empty"):
        return html.P("No expenses for this selection.")
    if not summary["tuition_ready"]:
        return html.P(
            f"Total expenses {_money(summary['total'])}. "
            "Charter tuition and special-education tuition are not split out until the AFR tuition schedule is published."
        )
    bits = [
        html.Span(f"Total expenses {_money(summary['total'])}. ", className="me-3"),
        html.Span(f"Charter tuition in that total {_money(summary['charter_removed'])}. ", className="me-3"),
        html.Span(
            f"Special education tuition kept {_money(summary['sped_kept'])} "
            "(approved private schools and PRRIs). ",
            className="me-3",
        ),
    ]
    if summary["per_pupil"] is None:
        bits.append(html.Span("Per pupil is not available until the AFR tuition schedule is published."))
    else:
        bits.append(
            html.Span(
                f"Per pupil {_money(summary['per_pupil'])} "
                f"on {summary['enrollment']:,.0f} enrolled students, after removing charter tuition."
            )
        )
    return html.P(bits, className="mb-1")


app.layout = _layout


def main() -> None:
    app.run(debug=False, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
