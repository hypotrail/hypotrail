"""Companion du tutoriel : CLI, webview message passing et secours HTTP local."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import secrets
import sys
import uuid
import importlib.util
_spec=importlib.util.spec_from_file_location('hypotrail_tutorial_protocol',Path(__file__).resolve().parent/'protocol.py')
protocol=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(protocol)

ROOT=Path(__file__).resolve().parent
connect=protocol.connect
snapshot=protocol.snapshot
valid=protocol.valid

def make_server(path,token,port):
    with __import__('contextlib').closing(connect(path)):pass
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,code,payload,mime='application/json'):
            body=json.dumps(payload,ensure_ascii=False).encode() if mime=='application/json' and not isinstance(payload,bytes) else payload
            self.send_response(code)
            for key,value in {'Content-Type':mime+'; charset=utf-8','Content-Length':str(len(body)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(body)
        def allowed(self):
            host=f'127.0.0.1:{self.server.server_port}'
            return self.headers.get('Host')==host and self.headers.get('Origin') in (None,'http://'+host) and hmac.compare_digest(self.headers.get('X-Pilot-Token',''),token)
        def do_GET(self):
            assets={'/':'companion.html','/companion.js':'companion.js','/bridge.js':'bridge.js','/markdown.js':'markdown.js','/design.css':'design.css'}
            if self.path in assets:
                if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':return self.send(403,{'error':'host'})
                file=ROOT/assets[self.path];mime='text/css' if file.suffix=='.css' else 'text/javascript' if file.suffix=='.js' else 'application/json' if file.suffix=='.json' else 'text/html'
                return self.send(200,file.read_bytes(),mime)
            if self.path!='/state':return self.send(404,{'error':'not found'})
            if not self.allowed():return self.send(403,{'error':'session required'})
            return self.send(200,protocol.status(path))
        def do_POST(self):
            if self.path not in ('/state','/rpc'):return self.send(404,{'error':'not found'})
            if not self.allowed():return self.send(403,{'error':'session required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=32768:return self.send(413,{'error':'payload size'})
                payload=json.loads(self.rfile.read(length))
                if self.path=='/state':
                    if set(payload)!={'expected_revision','state'} or not valid(payload['state']):raise protocol.ProtocolError('schema','Invalid exercise state')
                    current=protocol.status(path)
                    payload={'action':'submit','event':{'protocol_version':1,'event_id':uuid.uuid4().hex,'session_id':current['session_id'],'expected_revision':payload['expected_revision'],'context_hash':current['context_hash'],'type':'submit_state','payload':{'state':payload['state']}}}
                if payload.get('action')=='explain':raise protocol.ProtocolError('action','The explanation comes from the pilot through the CLI.')
                if payload.get('action') not in ('status','project','submit','apply','export','confirm_fact'):raise protocol.ProtocolError('action','Action reserved for the VS Code companion.')
                return self.send(200,protocol.dispatch(path,payload))
            except protocol.ProtocolError as e:return self.send(e.status,{'error':e.code,'message':str(e)})
            except (ValueError,TypeError,KeyError):return self.send(400,{'error':'invalid request'})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['serve','status','explain','apply','export','rpc','validate'])
    parser.add_argument('--project',help='registry identifier from projects/registry.json (default: default project)')
    parser.add_argument('--db',type=Path,default=None,help='default: project .local/<session_name>.sqlite');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--message');parser.add_argument('--event');parser.add_argument('--expected-revision',type=int);parser.add_argument('--context-hash')
    parser.add_argument('--application-event',help='explain: attach the message to the applied choice (with --context-hash)')
    args=parser.parse_args()
    try:protocol.use_project(args.project)
    except ValueError as e:
        print(json.dumps({'error':getattr(e,'code','config'),'message':str(e)},ensure_ascii=False));return 2
    args.db=args.db or ROOT/'.local'/(protocol.bundle()['project']['session_name']+'.sqlite')
    if args.action=='validate':
        b=protocol.bundle();print(json.dumps({'project':b['project']['id'],'journey':b['journey']['id'],'activities':len(b['journey']['activities']),'choices':sorted(b['choices']),'dataset_changed':b['dataset_changed'],'context_hash':b['context_hash']},ensure_ascii=False,indent=2));return 0
    if args.action=='serve':
        token=secrets.token_urlsafe(32);server=make_server(args.db,token,args.port)
        print(f'Ouvrir : http://127.0.0.1:{server.server_port}/#token={token}',flush=True)
        print('Tutorial only. No automatic Copilot wake-up or training.',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
        return 0
    try:
        if args.action=='rpc':
            raw=sys.stdin.read(131073)
            if len(raw)>131072:raise protocol.ProtocolError('size','Request too large.')
            request=json.loads(raw)
        elif args.action=='explain':
            request={'action':'explain','message':args.message}
            if args.application_event or args.context_hash:request.update(application_event_id=args.application_event,context_hash=args.context_hash)
        elif args.action=='apply':request={'action':'apply','event_id':args.event,'expected_revision':args.expected_revision,'context_hash':args.context_hash}
        else:request={'action':args.action}
        print(json.dumps(protocol.dispatch(args.db,request),ensure_ascii=False,indent=2));return 0
    except (protocol.ProtocolError,ValueError,TypeError) as e:
        print(json.dumps({'error':getattr(e,'code','invalid'),'message':str(e)},ensure_ascii=False));return 2
if __name__=='__main__':sys.exit(main())
