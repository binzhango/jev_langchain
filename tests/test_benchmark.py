import json
import pytest
from jev_harness.benchmark import cases, payload, validate, run, summarize, measure, lenient_result, wilson, scored_report
from jev_harness.config import Settings


def test_payload_does_not_leak_labels():
    suite = cases()
    assert len(suite) == 18
    for case in suite:
        request = payload(case)
        assert set(request) == {"state", "questions"}
        assert "expected" not in request and "id" not in request


@pytest.mark.parametrize("value", [float('nan'), float('inf'), -1, 3, True, '1'])
def test_invalid_scores_fail(value):
    with pytest.raises(ValueError):
        validate({'score': value}, {'type':'score','criteria':['routine','uncertain','severe']})


def test_paired_runner_counts_errors_and_excludes_warmups(tmp_path):
    seen=[]
    def invoke(provider,case):
        seen.append((provider,payload(case)))
        if provider=='llm' and case['question']['type']=='noul':
            raise ValueError('invalid JSON')
        return {case['question']['type']:case['expected']},{'input_tokens':10},provider,{}
    report=run(Settings(),tmp_path,repeat=2,limit=3,invoke=invoke)
    assert len(report['rows'])==12 and len(report['warmups'])==2
    assert report['summary']['llm']['failures']==2
    assert report['summary']['llm']['decision_accuracy']==pytest.approx(2/3)
    assert report['summary']['jev']['decision_accuracy']==1
    assert report['summary']['llm']['output_tokens'] is None
    for case in report['cases']:
        rows=[r for r in report['rows'] if r['case_id']==case['id']]
        assert len({r['input_hash'] for r in rows})==1
        assert len({r['order'] for r in rows if r['provider']=='llm'})==2
    assert json.loads((tmp_path/'report.json').read_text())['summary']==report['summary']
    assert (tmp_path/'report.html').exists()


def test_risk_errors_not_hidden_as_safe():
    rows=[{'provider':'jev','primitive':'score','status':'ok','value':0.9,'expected':1,'correct':False,'latency_ms':10,'usage':{}},
          {'provider':'jev','primitive':'score','status':'error','correct':False,'latency_ms':100,'usage':{}}]
    result=summarize(rows)['jev']
    assert result['decision_accuracy']==0
    assert result['false_allows']==1 and result['failures']==1
    assert result['latency_p50_ms']==10
    assert result['all_attempt_latency_p50_ms']==55


def test_failed_parsing_preserves_raw_output_and_usage():
    def invoke(provider, case):
        return 'not JSON', {'output_tokens': 7}, 'local', {'text': 'not JSON'}
    row = measure('llm', cases()[0], invoke, Settings(), 0, 0)
    assert row['status'] == 'error' and not row['correct']
    assert row['raw']['text'] == 'not JSON'
    assert summarize([row])['llm']['output_tokens'] == 7


@pytest.mark.parametrize('raw,expected_status', [
    ('{"decision": 1.0}', 'ok'), ('```json\n{"noul": 1.0}\n```', 'ok'),
    ('{"decision": {"noul": 1.0}}', 'ok'),
    ('{"decision": 1.0, "noul": 0.0}', 'error'), ('{"decision": "1.0"}', 'error'),
    ('{"decision": 2.0}', 'error'), ('{"decision": true}', 'error'),
    ('{"decision": 0.0, "decision": 1.0}', 'error'), ('The answer is yes.', 'error'),
])
def test_lenient_parsing_is_bounded_and_does_not_change_strict_score(raw, expected_status):
    row = {'status':'error', 'correct':False, 'raw':{'text':raw}, 'expected':1}
    result = lenient_result(row, {'type':'noul'})
    assert result['lenient_status'] == expected_status
    assert result['status'] == 'error' and not result['correct']
    assert row == {'status':'error', 'correct':False, 'raw':{'text':raw}, 'expected':1}


def test_wilson_intervals_do_not_count_repetitions_as_new_cases(tmp_path):
    def invoke(provider, case):
        return {case['question']['type']:case['expected']}, {}, provider, {}
    report = run(Settings(), tmp_path, repeat=3, limit=3, warmup=False, invoke=invoke)
    assert report['summary']['llm']['attempts'] == 9
    assert report['summary']['llm']['interval_cases'] == 3
    assert report['summary']['llm']['first_pass_strict_ci95'] == wilson(3, 3)
    assert wilson(18, 18)[0] == pytest.approx(.8241208, abs=1e-6)
    assert wilson(0, 18)[1] == pytest.approx(.1758792, abs=1e-6)
    assert wilson(0, 0) is None


def test_historical_field_slip_gets_lenient_credit_without_rewriting_evidence():
    from pathlib import Path
    report = json.loads((Path(__file__).parents[1] / 'docs/recordings/decision-benchmark-live.json').read_text())
    original = json.dumps(report, sort_keys=True)
    scored = scored_report(report)
    assert scored['summary']['llm']['failures'] == 1
    assert scored['summary']['llm']['lenient_correct'] == 18
    assert scored['summary']['llm']['lenient_recovered'] == 1
    assert json.dumps(report, sort_keys=True) == original
