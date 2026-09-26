"""Replay an observed factual error through the real repair and recheck stages.

Only the earlier verifier response is replayed; repair and recheck are paid.
No generation, bank update or publishing path is called. Uses a marked test run
in the normal cost ledger; safe alongside the daily job (no publication state writes).
"""
import argparse
import json
import pathlib
import sys
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pay', action='store_true')
    p.add_argument('--input', type=pathlib.Path, required=True)
    p.add_argument('--prompts', type=pathlib.Path, required=True)
    p.add_argument('--output', type=pathlib.Path, required=True)
    a = p.parse_args()
    if not a.pay or a.output.exists():
        p.error('Need --pay and a new output path')
    import db
    import config
    import llm
    import stages
    case = next(c for c in json.loads(a.input.read_text())['cases'] if c['id']=='quantization_comment')
    original = case['draft']
    audit = next(r['response'] for r in case['requests'] if r['purpose']=='factcheck')
    conn = db.connect()
    run_id = db.start_run(conn, stage='natural_repair_replay', tryb='test')
    result = {'run_id': run_id, 'original': original, 'status': 'RUNNING', 'publishing_called': False}
    try:
        with patch.object(config, 'PROMPTS_DIR', a.prompts.resolve()):
            with patch.object(llm, 'call', return_value=json.dumps(audit)):
                normalized = stages.zweryfikuj(conn, run_id, original, case['title'])
            words = len(original.split())
            fixed = stages.napraw_obalone(conn, run_id, original, normalized,
                         kontekst=case['title'], min_slow=max(4,int(words*.5)),
                         max_slow=max(12,int(words*1.5)), etap='naprawa_komentarza',
                         zapora=stages._zapora_komentarza)
        result['repair'] = fixed
        assert fixed and fixed['sprawdzona'], 'Repair not accepted and verified'
        result['status'] = 'DONE'
        db.finish_run(conn, run_id, 'DONE', note='Replay observed claim through natural repair; no publication')
    except BaseException as exc:
        result['status'] = 'FAILED'
        result['error'] = str(exc)
        db.finish_run(conn, run_id, 'FAILED', note=str(exc)[:500])
        raise
    finally:
        result['calls'] = [dict(r) for r in conn.execute('SELECT model,purpose,tokens_in,tokens_out,web_searches,cost_usd,ok,price_verified FROM calls WHERE run_id=?',(run_id,))]
        result['cost_usd_estimated'] = sum(c['cost_usd'] for c in result['calls'])
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
        conn.close()
        print(json.dumps(result.get('repair'),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
