"""Exercise transitions cannot ratify the project or create a fit."""
import importlib.util
from pathlib import Path
import json
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('osml_protocol',ROOT/'protocol.py');protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)

def event(db,answers,step=5,key='test-choice'):
 s=protocol.status(db)
 return {'protocol_version':1,'event_id':key,'session_id':s['session_id'],'expected_revision':s['revision'],'context_hash':s['context_hash'],'type':'submit_state','payload':{'state':{'step':step,'answers':answers}}}

def test_registration_application_and_existing_result_are_distinct(tmp_path):
 db=tmp_path/'session.sqlite';request=event(db,{'threshold':.2})
 registered=protocol.submit(db,request)
 assert registered['pending_event_id']=='test-choice' and registered['application'] is None
 applied=protocol.apply(db,'test-choice',registered['revision'],registered['context_hash'])
 assert applied['application']['current'] and applied['application']['result']['metrics']['alerts']==75
 assert applied['application']['result']['new_fits']==0 and applied['project_approval'] is False
 assert [x['type'] for x in applied['events']]==['choice_registered','choice_applied','result_selected']
 assert protocol.apply(db,'test-choice',registered['revision'],registered['context_hash'])['receipt']['replayed']

def test_network_retry_is_idempotent_and_reused_id_rejected(tmp_path):
 db=tmp_path/'session.sqlite';request=event(db,{'goal':0});first=protocol.submit(db,request)
 second=protocol.submit(db,request);assert second['receipt']['replayed'] and first['revision']==second['revision']
 request['payload']['state']['answers']['goal']=1
 with pytest.raises(protocol.ProtocolError,match='reused'):protocol.submit(db,request)

def test_two_clients_and_context_rejected(tmp_path):
 db=tmp_path/'session.sqlite';a=event(db,{'goal':0},key='a');b=event(db,{'goal':1},key='b')
 protocol.submit(db,a)
 with pytest.raises(protocol.ProtocolError,match='tab'):protocol.submit(db,b)
 c=event(db,{},key='c');c['context_hash']='other'
 with pytest.raises(protocol.ProtocolError,match='changed'):protocol.submit(db,c)

def test_navigation_does_not_apply_or_supersede_choice(tmp_path):
 db=tmp_path/'session.sqlite';s=protocol.submit(db,event(db,{'baseline':0},key='choice'))
 s=protocol.submit(db,event(db,{'baseline':0},step=4,key='read'))
 assert s['pending_event_id']=='choice' and s['application'] is None
 applied=protocol.apply(db,'choice',s['revision'],s['context_hash']);assert applied['application']['result'] is None

def test_changed_choice_invalidates_prior_application(tmp_path):
 db=tmp_path/'session.sqlite';s=protocol.submit(db,event(db,{'threshold':.2},key='first'))
 s=protocol.apply(db,'first',s['revision'],s['context_hash'])
 s=protocol.submit(db,event(db,{'threshold':.5},key='second'))
 assert not s['application']['current'] and s['pending_event_id']=='second'

@pytest.mark.parametrize('payload',[{'approve_project':1},{'threshold':.75},{'goal':True},{'shell':'rm'},{'mode':'auto'}])
def test_unsupported_actions_and_project_approval_rejected(tmp_path,payload):
 db=tmp_path/'session.sqlite'
 with pytest.raises(protocol.ProtocolError):protocol.submit(db,event(db,payload))

def test_restart_and_cli_see_same_event_and_explanation(tmp_path):
 db=tmp_path/'session.sqlite';s=protocol.submit(db,event(db,{'threshold':.35}))
 read=json.loads(subprocess.check_output([sys.executable,str(ROOT/'bridge.py'),'status','--db',str(db)]))
 assert read['pending_event_id']==s['pending_event_id']
 subprocess.run([sys.executable,str(ROOT/'bridge.py'),'apply','--db',str(db),'--event',s['pending_event_id'],'--expected-revision',str(s['revision']),'--context-hash',s['context_hash']],check=True,capture_output=True)
 subprocess.run([sys.executable,str(ROOT/'bridge.py'),'explain','--db',str(db),'--message','This threshold selects 43 contacts in this precomputed example.'],check=True,capture_output=True)
 state=protocol.status(db);assert state['application']['result']['metrics']['alerts']==43 and state['pilot_message'].startswith('This threshold')
 assert state['project_approval'] is False


def test_choice_cannot_apply_after_results_context_changes(tmp_path, monkeypatch):
 db=tmp_path/'session.sqlite';old=protocol.submit(db,event(db,{'threshold':.2}))
 monkeypatch.setattr(protocol,'context_hash',lambda:'changed-results')
 with pytest.raises(protocol.ProtocolError,match='another result version'):
  protocol.apply(db,'test-choice',old['revision'],'changed-results')
