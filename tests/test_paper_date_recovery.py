import ast
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from paper_date import publication_window, papers_on_date
import main

class RecoveryTests(unittest.TestCase):
    def test_day_bounds_and_filter(self):
        start, end = publication_window('2026-10-10')
        self.assertEqual((end-start).total_seconds(), 86400)
        papers = [{'id': str(i), 'published': d} for i,d in enumerate([
            '2026-10-09T23:59:59Z','2026-10-10T00:00:00Z',
            '2026-10-10T23:59:59Z','2026-10-11T00:00:00Z','',
            '2026-10-10T00:00:00', '2026-10-11T01:00:00+02:00'])]
        self.assertEqual([p['id'] for p in papers_on_date(papers,'2026-10-10')], ['1','2','6'])
        for bad in ['2026-10-32', '20261010', '2026-1-01']:
            with self.assertRaises(ValueError): publication_window(bad)

    def test_both_recall_windows_override_nine_days(self):
        for filename in ['2.1.retrieval_papers_bm25.py','2.2.retrieval_papers_embedding.py']:
            tree=ast.parse((ROOT/'src'/filename).read_text())
            fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='resolve_supabase_recall_window')
            env={'os':os,'Dict':dict,'Any':object,'datetime':datetime,'timezone':timezone}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),filename,'exec'),env)
            with patch.dict(os.environ, {'DPR_PAPER_DATE':'2026-10-10'}):
                self.assertEqual(env[fn.name]({'arxiv_paper_setting':{'days_window':9}}),publication_window('2026-10-10'))

    def test_zero_source_stops_before_archive(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(main,'ROOT_DIR',tmp), patch.object(main,'should_skip_fetch',return_value=True), patch.object(main,'run_step') as run, patch('paper_date.require_source_day',side_effect=ValueError('source has 0 papers')):
            with patch.object(sys,'argv',['main.py','--paper-date','2026-10-16']), self.assertRaises(SystemExit): main.main()
            run.assert_not_called()
            self.assertFalse((Path(tmp)/'archive').exists())

    def test_main_propagates_date_and_rejects_existing_target(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(main,'ROOT_DIR',tmp), patch.object(main,'should_skip_fetch',return_value=True), patch.dict(os.environ,{},clear=False), patch.object(main,'run_step') as run, patch('paper_date.require_source_day',return_value=10):
            with patch.object(sys,'argv',['main.py','--paper-date','2026-10-10']): main.main()
            self.assertEqual(os.environ['DPR_RUN_DATE'],'20261010')
            self.assertEqual(os.environ['DPR_PAPER_DATE'],'2026-10-10')
            self.assertFalse(any('fetch arxiv' in c.args[0] for c in run.call_args_list))
            (Path(tmp)/'archive'/'20261010').mkdir(parents=True)
            run.reset_mock()
            with patch.object(sys,'argv',['main.py','--paper-date','2026-10-10']), self.assertRaises(SystemExit): main.main()
            run.assert_not_called()

    def test_empty_day_preserves_carryover(self):
        spec=importlib.util.spec_from_file_location('select_recovery',ROOT/'src'/'5.select_papers.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as tmp:
            carry=Path(tmp)/'carryover.json';carry.write_text('{"sentinel":true}')
            with patch.dict(os.environ,{'DPR_PAPER_DATE':'2026-10-10'}), patch.object(mod,'CARRYOVER_PATH',str(carry)), patch.object(mod,'TODAY_STR','20261010'), patch.object(mod,'load_arxiv_paper_setting',return_value={'mode':'standard'}), patch.object(mod,'load_config_tag_count',return_value=(0,[])), patch.object(mod,'collect_seen_ids',return_value=set()), patch.object(mod,'load_recent_carryover') as old, patch.object(sys,'argv',['select','--input',str(Path(tmp)/'missing.json'),'--output-dir',str(Path(tmp)/'out')]):
                mod.main()
                old.assert_not_called()
            self.assertEqual(carry.read_text(),'{"sentinel":true}')

if __name__=='__main__':unittest.main()
