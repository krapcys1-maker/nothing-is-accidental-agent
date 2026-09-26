"""Paid production draft generation on source-backed difficult topics.

Runs the real analysis -> note assembly, or real comment assembly. Stops after
the writer's response, before fact-check/repair/publication. --pay is mandatory.
An optional prompt directory tests a release candidate without deploying it.
"""
import argparse
import hashlib
import json
import pathlib
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class DraftReady(BaseException):
    pass


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pay', action='store_true')
    parser.add_argument('--cases', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--prompts', type=pathlib.Path)
    parser.add_argument('--systems', type=pathlib.Path)
    parser.add_argument('--full', action='store_true', help='Continue through factual checks and repairs; never publish')
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    if not args.pay:
        parser.error('--pay is required')
    if args.output.exists():
        parser.error('Output already exists; inspect it before paying again')
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    if args.case:
        cases = [c for c in cases if c['id'] in args.case]
    if not cases:
        parser.error('No cases selected')
    import fcntl
    import config
    import db
    import llm
    import stages
    protected = [config.DATA_DIR/n for n in ['dziennik.jsonl', 'indeks_kandydatow.json']]
    with (config.DATA_DIR/'agent.lock').open('a+') as lock, ExitStack() as stack:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.prompts:
            stack.enter_context(patch.object(config, 'PROMPTS_DIR', args.prompts.resolve()))
        if args.systems:
            systems = json.loads(args.systems.read_text(encoding='utf-8'))
            assert set(systems) <= {'NOTE_SYSTEM', 'COMMENT_SYSTEM'}
            for name, value in systems.items():
                stack.enter_context(patch.object(stages, name, value))
        before = {str(p): digest(p) for p in protected}
        conn = db.connect()
        run_id = db.start_run(conn, stage='natural_short_voice_test', tryb='test')
        result = {'run_id': run_id, 'status': 'RUNNING',
                  'started_at': datetime.now(timezone.utc).isoformat(),
                  'scope': ('Real stage including factual checks and repairs; never publish' if args.full else
                            'Real paid analysis and writer calls; stop before fact-check, repair and publication'),
                  'prompt_hashes': {p.name: digest(p) for p in sorted(config.PROMPTS_DIR.glob('*.md'))},
                  'cases': []}
        def save():
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        save()
        real_call = llm.call
        try:
            for case in cases:
                item = dict(case, requests=[])
                result['cases'].append(item)
                def call(purpose, system, user, **kwargs):
                    allowed = ('rozbior', 'note', 'comment', 'factcheck', 'naprawa', 'naprawa_komentarza') if args.full else ('rozbior', 'note', 'comment')
                    if purpose not in allowed:
                        raise AssertionError('Unexpected paid stage: '+purpose)
                    raw = real_call(purpose, system, user, **kwargs)
                    response = llm.parse_json(raw)
                    item['requests'].append(dict(purpose=purpose, system=system,
                                                 prompt=user, response=response))
                    save()
                    if purpose in ('note', 'comment'):
                        field = purpose
                        assert field in response, 'Missing draft field'
                        item['draft'] = response[field]
                        item['words'] = len((response[field] or '').split())
                        save()
                        if not args.full:
                            raise DraftReady()
                    return raw
                with patch.object(llm, 'call', side_effect=call):
                    try:
                        if case['kind'] == 'note':
                            final = stages.note(conn, run_id, 'CIEKAWOSTKA',
                                        {'fact': case['evidence'], 'url': case['url']},
                                        note_form=case.get('form', 'WYJASNIENIE'))
                        else:
                            final = stages.comment_on(conn, run_id,
                                              {'text': case['evidence'], 'title': case['title'],
                                               'author': case['author'], 'url': case['url']})
                        if args.full:
                            item['stage_result'] = final
                            save()
                    except DraftReady:
                        pass
                assert 'draft' in item, 'No writer response'
                print(json.dumps({'case': case['id'], 'draft': item['draft']}, ensure_ascii=False), flush=True)
            assert before == {str(p): digest(p) for p in protected}, 'Protected publication state changed'
            result['publication_state_unchanged'] = True
            result['status'] = 'DONE'
            db.finish_run(conn, run_id, 'DONE', note='Natural short-form source-backed drafts; no publication')
        except BaseException as exc:
            result['status'] = 'FAILED'
            result['error'] = type(exc).__name__+': '+str(exc)[:500]
            db.finish_run(conn, run_id, 'FAILED', note=result['error'])
            raise
        finally:
            result['calls'] = [dict(r) for r in conn.execute(
                'SELECT model,purpose,tokens_in,tokens_out,cache_hit,web_searches,cost_usd,ok,price_verified FROM calls WHERE run_id=?', (run_id,))]
            result['cost_usd_estimated'] = sum(c['cost_usd'] for c in result['calls'])
            result['finished_at'] = datetime.now(timezone.utc).isoformat()
            save()
            conn.close()


if __name__ == '__main__':
    main()
