import csv
import json
from html.parser import HTMLParser

from fallbackledger import replay, summarize, validate
from fallbackledger.report import write_report


class InspectHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)

    def handle_data(self, data):
        self.text.append(data)


def test_report_escapes_values_and_preserves_exact_sources(tmp_path, data):
    bad = '<script>alert("x")</script> & newline\ntext'
    data[2][2]["reason"] = bad
    data[0]["description"] = bad
    v = validate(*data).validated
    r = replay(v)
    s = summarize(v, r)
    paths = write_report(v, r, s, tmp_path / "report")
    html = (tmp_path / "report" / "report.html").read_text()
    parser = InspectHTML()
    parser.feed(html)
    assert "script" not in parser.tags
    assert not any(k in ("href", "src") or k.startswith("on") for k, v in parser.attrs)
    assert bad in "".join(parser.text)
    assert "conditional_on_usable_output" in html and "unknown_interval" in html
    assert len(paths) == 8


def test_json_csv_and_text_metrics_agree(tmp_path, data):
    v = validate(*data).validated
    r = replay(v)
    s = summarize(v, r)
    write_report(v, r, s, tmp_path / "report")
    summary = json.loads((tmp_path / "report" / "summary.json").read_text())
    with (tmp_path / "report" / "metrics.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(summary["metrics"])
    for csvrow, jsonrow in zip(rows, summary["metrics"]):
        assert csvrow["metric"] == jsonrow["metric"]
        assert int(csvrow["n"]) == jsonrow["n"]
        if jsonrow["value"] is not None:
            assert float(csvrow["value"]) == jsonrow["value"]
    text = (tmp_path / "report" / "summary.txt").read_text()
    assert "3.25" in text and "4/6" in text and "independent" in text.lower()
    with (tmp_path / "report" / "cohorts.csv").open(newline="") as f:
        memberships = list(csv.DictReader(f))
    assert len(memberships) == sum(len(c.rows) for c in s.cohorts)


def test_standalone_reports_show_declared_truth_and_nominal_level(tmp_path, data):
    scenario = '<scenario>&"quoted"'
    data[0]["scenarios"][0].update(id=scenario, truth=0.125)
    for row in data[1]:
        row["scenario_id"] = scenario
    for row in data[2]:
        row["scenario_id"] = scenario
    v = validate(*data).validated
    r = replay(v)
    write_report(v, r, summarize(v, r), tmp_path / "report")
    text = (tmp_path / "report" / "summary.txt").read_text()
    html = (tmp_path / "report" / "report.html").read_text()
    parser = InspectHTML()
    parser.feed(html)
    rendered = "".join(parser.text)
    for output in (text, rendered):
        assert "Declared scenario truth" in output
        assert scenario in output and "0.125" in output
        assert "Nominal interval level" in output and "0.95" in output
    assert "scenario" not in parser.tags
    assert "&lt;scenario&gt;&amp;&quot;quoted&quot;" in html


def test_point_only_report_does_not_invent_nominal_level(tmp_path, data):
    data[0]["metrics"].remove("coverage")
    data[0].pop("nominal_interval_level")
    v = validate(*data).validated
    r = replay(v)
    write_report(v, r, summarize(v, r), tmp_path / "report")
    for name in ("summary.txt", "report.html"):
        text = (tmp_path / "report" / name).read_text()
        assert "Nominal interval level" not in text
        assert "Declared scenario truth" in text
