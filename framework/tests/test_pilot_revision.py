"""Functional safety and integrity regressions introduced by review."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from mlkit import core, config, pilot
from mlkit.reference import ExistingScore
from mlkit.run import valid_stop_decision

@pytest.fixture
def project(tmp_path,monkeypatch):
 source=Path(__file__).resolve().parent / "fixtures/legacy-project"
 for name in ['questions.yaml','answers.yaml','frame.yaml','features.yaml']:(tmp_path/name).write_bytes((source/name).read_bytes())
 monkeypatch.setattr(config,'ROOT',tmp_path)
 monkeypatch.setattr(config,'REGISTRY_FILE',tmp_path/'registry.jsonl')
 (tmp_path/'model').mkdir();(tmp_path/'model/pipeline.py').write_text('FEATURES=[]\n')
 (tmp_path/'reports').mkdir()
 return tmp_path

def test_numeric_reference_preserves_unseen_order():
 m=ExistingScore('x',riskier='higher').fit(pd.DataFrame({'x':[0.,1.]}))
 assert np.all(np.diff(m.predict_proba(pd.DataFrame({'x':[2.,3.,4.,5.]}))[:,1])>0)
 assert m.predict_proba(pd.DataFrame({'x':[np.nan]}))[0,1]==1

def test_duplicate_category_refused():
 with pytest.raises(ValueError):ExistingScore('x',order=['A','A']).fit(pd.DataFrame({'x':['A']}))

@pytest.mark.parametrize('ids',[ [1,1], [1,3]])
def test_join_neither_duplicates_nor_silently_discards(tmp_path,ids):
 pd.DataFrame({'id':[1,2],'date':['2020-01']*2}).to_csv(tmp_path/'features.csv.gz',index=False)
 pd.DataFrame({'id':ids,'y':[0,1]}).to_csv(tmp_path/'labels.csv.gz',index=False)
 with pytest.raises(ValueError):core.load_split(tmp_path,{'id_col':'id','target_col':'y','time_col':'date'})

def test_sample_refuses_minority_over_cap():
 with pytest.raises(ValueError):core.training_sample(np.arange(1000)[:,None],np.array([1]*400+[0]*600),{'training_sample':{'max_rows':300,'keep_minority':True}})

def test_empty_stop_is_not_decision(tmp_path):
 p=tmp_path/'s.md';p.write_text('');assert not valid_stop_decision(p)
 p.write_text('Decision: RESUME\nSigned: Test human\nReason: Corrected data\nDate: 2026-10-17\n');assert valid_stop_decision(p)

def test_assumption_does_not_become_confirmation(project):
 s=pilot.init('auto');q=pilot.pending(s)[0]['id'];pilot.propose(s,q,'Hypothesis','Reason')
 assert q in {x['id'] for x in pilot.pending(s)}
 assert 'HUMAN' not in json.dumps(s['answers'][q])
 assert (project/'reports/pilot.html').exists()

def test_blind_bundle_and_tamper_detection(project):
 s=pilot.init('senior');d=pilot.dispatch(s,'leak-reviewer','Look for leakage')
 folder=Path(d['working_directory']);assert not (folder/'input/frame.yaml').exists()
 (folder/'input/features.yaml').write_text('tampered')
 with pytest.raises(ValueError,match='Input changed'):pilot.receive(s,d['task'])

def test_result_requires_evidence_and_no_escape(project):
 s=pilot.init('junior');d=pilot.dispatch(s,'feature-builder','Transform without a target');folder=Path(d['working_directory'])
 result={'summary':'Proposal','recommendation':'No change','findings':[],'tradeoffs':[],'artifacts':['../../../../answers.yaml']}
 (folder/'output/result.json').write_text(json.dumps(result))
 with pytest.raises(ValueError,match='outside output'):pilot.receive(s,d['task'])
 result['artifacts']=[];(folder/'output/result.json').write_text(json.dumps(result))
 assert pilot.receive(s,d['task'])['status']=='reported'

def test_html_does_not_execute_untrusted_answer(project):
 s=pilot.init('junior');q=pilot.pending(s)[0]['id'];pilot.propose(s,q,'<script>alert(1)</script>','Untrusted data')
 doc=pilot.render(s).read_text();assert '<script>alert(1)</script>' not in doc
 assert '&lt;script&gt;alert(1)&lt;/script&gt;' in doc

def test_single_writer(project):
 with pilot.lock():
  with pytest.raises(ValueError,match='already active'):
   with pilot.lock():pass

def test_no_confirmatory_path_in_revision(project):
 from mlkit.holdout import main
 with pytest.raises(SystemExit,match='suspended'):main(['--prereg','anything.yaml'])

def test_changed_contract_invalidates_steps_and_confirmation(project):
 s=pilot.init('senior');q=pilot.pending(s)[0]['id'];pilot.propose(s,q,'Yes','The person confirms',status='confirmed')
 s['steps']['profile']={'returncode':0};s['executions']=3;s['seconds_used']=42
 (project/'frame.yaml').write_text((project/'frame.yaml').read_text()+'\n# modification\n')
 pilot.sync_context(s)
 assert s['steps']=={} and s['answers'][q]['status']=='reconfirm'
 assert s['executions']==3 and s['seconds_used']==42

def test_timeout_budget_does_not_launch_more_work(project):
 s=pilot.init('auto');s['seconds_used']=s['max_seconds']
 assert 'Budget reached' in pilot.step(s)
 assert s['steps']=={}


def test_missing_contract_applies_at_scoring():
 from mlkit.score import row_violations
 violations=row_violations(pd.DataFrame({'x':[1.,np.nan]}),{'x':{'type':'numeric','max_missing':0}})
 assert violations.tolist()==['','x']

def test_ratify_or_revise_then_launch_new_autonomous_cycle(project):
 s=pilot.init('auto');q='Q-CAD-02';pilot.propose(s,q,'90%','Contract hypothesis')
 s['steps']={'profile':{'returncode':0}};s['seconds_used']=12;s['executions']=1
 pilot.dispatch(s,'leak-reviewer','Review the initial version')
 changes=project/'revision.json';changes.write_text(json.dumps({'question':q,'answer':'80%','rationale':'Human confirmation','updates':{'spec.evaluation.decision_rate':0.8,'spec.metric_primary':'bad_rate_at_approval_80'}}))
 before=s['context'];out=pilot.revise(s,changes,before)
 assert out['invalidated_steps']==['profile']
 assert config.load_yaml(project/'frame.yaml')['spec']['evaluation']['decision_rate']==0.8
 assert config.load_yaml(project/'answers.yaml')[q]['by']=='HUMAN'
 assert 'iterate' in pilot.step(s)
 pilot.iterate(s,'Recalculate after capacity change')
 assert s['iteration']==2 and s['seconds_used']==0 and s['executions']==0
 assert s['answers'][q]['status']=='confirmed' and s['tasks'][0]['status']=='stale'
 assert (project/'.pilot/iterations/0001/frame.yaml').exists()
 assert config.load_yaml(project/'.pilot/iterations/0001/frame.yaml')['spec']['evaluation']['decision_rate']==0.9

def test_stale_revision_is_rejected(project):
 s=pilot.init('auto')
 with pytest.raises(ValueError,match='stale'):pilot.revise(s,project/'not-read.json','old-context')


def test_iteration_snapshot_preserves_raw_step_logs(project):
 s=pilot.init('auto');folder=project/'.pilot/logs';folder.mkdir();(folder/'profile.txt').write_text('previous evidence')
 pilot.iterate(s,'New decision')
 (folder/'profile.txt').write_text('new evidence')
 assert (project/'.pilot/iterations/0001/.pilot/logs/profile.txt').read_text()=='previous evidence'

@pytest.mark.parametrize('explicit_sync',[True,False])
def test_stale_agent_result_refused_after_context_change(project,explicit_sync):
 s=pilot.init('senior');d=pilot.dispatch(s,'explorer','Analyze the contract')
 folder=Path(d['working_directory'])
 (folder/'output/result.json').write_text(json.dumps({'summary':'Previous context','recommendation':'Retain','findings':[],'tradeoffs':[],'artifacts':[]}))
 (project/'frame.yaml').write_text((project/'frame.yaml').read_text().replace('decision_rate: 0.9','decision_rate: 0.8'))
 if explicit_sync:pilot.sync_context(s)
 with pytest.raises(ValueError):pilot.receive(s,d['task'])
 assert s['tasks'][0]['status']=='stale'

def test_retry_invalidates_downstream_without_free_budget(project):
 s=pilot.init('auto');s['steps']={k:{'returncode':0} for k in ['pipeline','evaluate','residuals','render','notebooks']}
 s['executions']=5;s['seconds_used']=42
 pilot.dispatch(s,'explorer','Analyze results')
 result=pilot.retry(s,'pipeline')
 assert set(result['invalidated_steps'])=={'pipeline','evaluate','residuals','render','notebooks'}
 assert not s['steps'] and s['tasks'][0]['status']=='stale'
 assert s['executions']==5 and s['seconds_used']==42

def test_revision_requires_reconfirmation_of_other_decisions(project):
 s=pilot.init('auto')
 for q in pilot.questions():pilot.propose(s,q['id'],'Yes','Previous context',status='confirmed')
 change=project/'revision.json';change.write_text(json.dumps({'question':'Q-CAD-01','answer':'New usage','rationale':'New demande','updates':{'spec.evaluation.decision_rate':0.8}}))
 pilot.revise(s,change,s['context'])
 assert s['answers']['Q-CAD-01']['status']=='confirmed'
 assert all(a['status']=='reconfirm' for q,a in s['answers'].items() if q!='Q-CAD-01')

def test_each_retry_preserves_its_own_logs(project):
 s=pilot.init('auto');logs=project/'.pilot/logs';logs.mkdir()
 for value in ['first','second']:
  (logs/'pipeline.txt').write_text(value);pilot.retry(s,'pipeline')
 snapshots=list((project/'.pilot/iterations').glob('*-retry-*/.pilot/logs/pipeline.txt'))
 assert {p.read_text() for p in snapshots}=={'first','second'}

def test_ticket_test_plan_enters_auto_and_expires_on_test_change(project):
 source=Path(__file__).resolve().parent / "fixtures/legacy-project"
 for rel in ['test-policy.json','ticket.example.json']:(project/rel).write_bytes((source/rel).read_bytes())
 pilot.init('auto')
 assert pilot.main(['tests','--ticket','ticket.example.json'])==0
 s=pilot.load()
 assert 'quality' in dict(pilot.remaining(s))
 assert 'PLAN_NOT_EXECUTED' in (project/'reports/pilot.html').read_text()
 s['steps']['quality']={'returncode':0,'seconds':1}
 (project/'tests').mkdir();(project/'tests/test_new.py').write_text('def test_new(): assert True\n')
 assert 'quality' in dict(pilot.remaining(s))
 assert 'quality' not in s['steps']

def test_pilot_tests_failure_is_visible_and_consumes_budget(project):
 source=Path(__file__).resolve().parent / "fixtures/legacy-project"
 (project/'ticket.json').write_bytes((source/'ticket.example.json').read_bytes())
 (project/'test-policy.json').write_text(json.dumps({'context_paths':['test-policy.json'], 'suites':[
  {'id':'failure','title':'Failure expected','changes':['model'],'phases':['pr'],
   'command':['{python}','-c','raise SystemExit(7)']}]}))
 pilot.init('auto')
 assert pilot.main(['tests','--ticket','ticket.json','--run'])==2
 s=pilot.load()
 assert s['executions']==1 and s['seconds_used']>0 and s['steps']['quality']['returncode']==2
 assert 'INCOMPLETE_OR_FAILED' in (project/'reports/pilot.html').read_text()

def test_auto_step_executes_selected_tests_in_project_root(project):
 source=Path(__file__).resolve().parent / "fixtures/legacy-project"
 (project/'ticket.json').write_bytes((source/'ticket.example.json').read_bytes())
 (project/'test-policy.json').write_text(json.dumps({'context_paths':['test-policy.json'], 'suites':[
  {'id':'smoke','title':'Execution inside the project','changes':['model'],'phases':['pr'],
   'command':['{python}','-c','from pathlib import Path; assert Path("ticket.json").exists()']}]}))
 s=pilot.init('auto');s['test_ticket']='ticket.json';s['test_phase']='pr'
 s['steps']={k:{'returncode':0,'seconds':0} for k,_ in pilot.TASKS}
 assert 'quality: code 0' in pilot.step(s)
 assert s['steps']['quality']['returncode']==0 and s['executions']==1
