// Transport (webview messages or local HTTP fallback), synchronization, and AI guidance.
// Generic: activities, choices, labels, and units come from window.osml (companion.js).
(() => {
  const vscode=typeof acquireVsCodeApi==='function'?acquireVsCodeApi():null;
  const osml=window.osml;
  if(!vscode && location.protocol==='file:'){
    const notice=document.getElementById('loading');
    notice.textContent='Open the companion in VS Code (Hypotrail: open companion) or through python bridge.py serve: the engine reads project configuration.';return;
  }
  const outstanding=new Map(),listeners=new Set();let serial=0;
  if(vscode)window.addEventListener('message',event=>{
    const data=event.data;
    if(data?.type==='assistant-event'){
      // Event from'another project (late response after switching) is ignored.
      if(data.project_id&&osml.bundle()&&data.project_id!==osml.bundle().project.id)return;
      for(const listener of listeners)listener(data);return;
    }
    if(data?.type!=='rpc-result'||!outstanding.has(data.id))return;
    const {resolve,reject,timer}=outstanding.get(data.id);clearTimeout(timer);outstanding.delete(data.id);
    if(data.error)reject(Object.assign(Error(data.error.message),{code:data.error.code}));else resolve(data.data);
  });
  const params=new URLSearchParams(location.hash.slice(1)),key='tutorial-bridge-token:'+location.origin;
  let token=params.get('token')||sessionStorage.getItem(key)||'';
  if(token){sessionStorage.setItem(key,token);history.replaceState(null,'',location.pathname)}
  function call(message,timeoutMs=15000){
    return new Promise((resolve,reject)=>{
      const id=String(++serial),timer=setTimeout(()=>{outstanding.delete(id);reject(Object.assign(Error('The engine is not responding. Verify the choice before continuing.'),{code:'timeout'}))},timeoutMs);
      outstanding.set(id,{resolve,reject,timer});vscode.postMessage({...message,id});
    });
  }
  async function rpc(request){
    if(vscode)return call({type:'rpc',request});
    const response=await fetch('/rpc',{method:'POST',headers:{'X-Pilot-Token':token,'Content-Type':'application/json'},body:JSON.stringify(request)});
    const result=await response.json();if(!response.ok)throw Object.assign(Error(result.message||'Connection refused'),{code:result.error});return result;
  }
  const host=(op,payload,timeoutMs)=>call({type:'assistant',op,payload},timeoutMs);
  const bar=document.createElement('section');bar.className='connection-panel';bar.dataset.sync='loading';
  bar.innerHTML='<div class="connection-heading"><span class="label">Connection to the pilot</span><span id="transport-badge"></span></div><p id="sync-status" role="status" aria-live="polite"></p><p id="pilot-message"></p><div class="connection-actions"><button id="apply-exercise" class="primary" disabled>Apply in the exercise</button></div><details class="connection-more" id="technical"><summary>Technical state</summary><div class="state-track"><div><span class="phase-number">01</span><h3>Recorded choice</h3><p id="record-status">Loading…</p></div><div><span class="phase-number">02</span><h3>Applied choice</h3><p id="apply-status">No attested application.</p></div><div><span class="phase-number">03</span><h3>Available result</h3><p id="result-status">No new calculation.</p></div></div><p class="small" id="technical-ids"></p></details><details class="connection-more"><summary>Conversation and export</summary><div class="connection-actions"><button id="reload-shared">Reload shared state</button><button id="copy-resume">Copy for Copilot</button><button id="export-session">Export session JSON</button></div><p class="small">Tutorial only. Reading clicks are not decisions. Only Apply and explain, Send, and quick questions request a model; Copilot chat is never opened.</p></details>';
  document.querySelector('main > div').prepend(bar);
  const $=id=>document.getElementById(id),sync=$('sync-status');
  $('transport-badge').textContent=vscode?'In VS Code':'Application locale';$('transport-badge').dataset.transport=vscode?'webview':'http';$('transport-badge').title=vscode?'Local message passing without an HTTP server':'Secours HTTP local';
  const stable=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
  const shape=s=>({activity:s.activity,answers:s.answers});
  let current=null,ready=false,busy=false,queued=null,inflight=null,conflict=false,last='';
  const conflictCodes=new Set(['stale_revision','context','session','id_reused','superseded','stale_context']);
  let assistant=null;
  function display(data){
    current=data;osml.setSnapshot(data);
    $('record-status').textContent=data.pending_event_id?'En pending d’application.':Object.keys(data.state.answers).length?'Choices retained.':'No choice.';
    const applied=data.application;
    $('apply-status').textContent=applied?(applied.current?'Applied in the exercise · revision '+applied.revision:'Previous choice; review required.'):'Not applied.';
    $('result-status').textContent=applied?.result?(applied.current?'Precomputed · no new training.':'Previous result.'):'No associated result.';
    $('technical-ids').textContent='Project '+data.project_id+' · journey '+data.journey.id+' v'+data.journey.version+' · session '+data.session_id+' · revision '+data.revision+' · results '+data.context_hash.slice(0,12)+(applied?' · application '+applied.event_id:'')+' · schema '+data.schema_version;
    if(!assistant){$('apply-exercise').hidden=!data.pending_event_id;$('apply-exercise').disabled=!data.pending_event_id||busy||conflict;}
    $('pilot-message').textContent=data.pilot_message||'The pilot can read these choices in the next exchange. It was not automatically activated.';
    // In VS Code, chat messages appear in the conversation only once.
    $('pilot-message').hidden=!data.pilot_message||Boolean(assistant);
    assistant?.sync(data);
  }
  async function load(){
    if(busy)return;
    try{
      ready=false;
      if(!osml.bundle()){osml.start(await rpc({action:'project'}));if(vscode&&!assistant)assistant=createAssistantPanel();}
      const data=await rpc({action:'status'});current=data;osml.setState(shape(data.state));last=stable(shape(data.state));queued=null;inflight=null;conflict=false;
      ready=true;display(data);osml.render();bar.dataset.sync='saved';sync.textContent='Connected · shared exercise choices.';assistant?.connected();
    }catch(e){bar.dataset.sync='offline';sync.textContent='Disconnected: '+e.message;if(['schema_version','config','component_unknown','journey_incompatible','path_forbidden','project_mismatch'].includes(e.code))$('content').innerHTML='<p class="notice" role="alert"></p>',$('content').firstChild.textContent='Configuration incompatible : '+e.message;}
  }
  function envelope(value){return {protocol_version:1,event_id:crypto.randomUUID().replaceAll('-',''),session_id:current.session_id,expected_revision:current.revision,context_hash:current.context_hash,type:'submit_state',payload:{state:value}};}
  async function flush(){
    if(busy||!ready||conflict||(!queued&&!inflight))return;
    busy=true;assistant?.refresh();if(!assistant)$('apply-exercise').disabled=true;
    if(!inflight){inflight=envelope(queued);queued=null;}
    try{
      const result=await rpc({action:'submit',event:inflight});
      const submitted=stable(inflight.payload.state);
      if(stable(shape(result.state))!==submitted){conflict=true;bar.dataset.sync='conflict';sync.textContent='Shared state changed. Local draft retained; review before reloading.';return;}
      last=submitted;inflight=null;display(result);bar.dataset.sync=queued?'saving':'saved';sync.textContent=queued?'Saving latest choices…':'Recorded choices · available to the pilot, without ratifying project decisions.';
    }catch(e){
      if(conflictCodes.has(e.code)){conflict=true;bar.dataset.sync='conflict';sync.textContent='Another tab changed the answers. Draft retained; review before reloading.';}
      else{bar.dataset.sync='offline';sync.textContent='Not synchronized: '+e.message+' · your draft remains visible.';}
    }finally{busy=false;if(current)display(current);if(!conflict&&(queued||inflight))setTimeout(flush,900);}
  }
  window.bridgeQueue=value=>{
    assistant?.refresh();
    if(!ready)return;const text=stable(value);if(!busy&&!inflight&&!queued&&text===last)return;
    queued=JSON.parse(text);
    if(conflict){bar.dataset.sync='conflict';sync.textContent='Shared state changed. Local draft retained; review before continuing.';return;}
    bar.dataset.sync='saving';sync.textContent='Saving latest choices…';flush();
  };
  osml.onConfirm=async(factId,decision)=>{
    try{const data=await rpc({action:'confirm_fact',fact_id:factId,decision});display(data);osml.render();sync.textContent=decision==='confirm'?'Information confirmed by you.':'Proposal rejected; the information still needs clarification.';}
    catch(e){sync.textContent=e.message;}
  };
  $('reload-shared').onclick=load;
  $('apply-exercise').onclick=async()=>{
    if(assistant)return assistant.applyAndExplain();
    if(busy||!current?.pending_event_id||conflict)return;
    busy=true;$('apply-exercise').disabled=true;
    const request={action:'apply',event_id:current.pending_event_id,expected_revision:current.revision,context_hash:current.context_hash};
    try{const data=await rpc(request);display(data);osml.render();sync.textContent='Choice applied in the exercise. No project decision changed.';bar.dataset.sync='saved';}
    catch(e){sync.textContent=e.message;conflict=conflictCodes.has(e.code);bar.dataset.sync=conflict?'conflict':'offline';}
    finally{busy=false;if(current)display(current);}
  };
  $('copy-resume').onclick=async()=>{
    const text='Resume the Hypotrail companion (project '+(osml.bundle()?.project.title||'')+'). Read its status and distinguish recorded choice, applied choice, and existing result. No exercise answer may become a project decision.';
    if(vscode)vscode.postMessage({type:'copy',text});else{try{await navigator.clipboard.writeText(text)}catch(_){sync.textContent=text;return;}}
    sync.textContent='Message copied. Paste it into Copilot; no message was sent automatically.';
  };
  $('export-session').onclick=async()=>{
    try{if(vscode){vscode.postMessage({type:'export'});return;}
      const data=await rpc({action:'export'});
      const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));link.download='hypotrail-session-'+data.project_id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
    }catch(e){sync.textContent=e.message;}
  };
  setInterval(async()=>{
    if(!ready||busy||queued||inflight||conflict||assistant?.applying())return;
    const observed=current.revision;
    try{const data=await rpc({action:'status'});if(busy||queued||inflight||current.revision!==observed)return;
      if(stable(shape(data.state))!==last){conflict=true;bar.dataset.sync='conflict';sync.textContent='Shared state changed. Reload before continuing.';assistant?.refresh();return;}
      const factsChanged=stable(data.facts)!==stable(current.facts);display(data);if(factsChanged)osml.render();
    }catch(_){sync.textContent='Engine unavailable; local state retained.';bar.dataset.sync='offline';}
  },2500);
  load();

  // ---------------- Accompagnement IA (webview VS Code uniquement) ----------------
  function createAssistantPanel(){
    const LIMIT=4000,HISTORY=10;
    const MODEL_ACTIONS={no_model:['retry','choose'],model_unavailable:['choose'],model_not_chosen:['choose'],access_denied:['retry'],quota:['retry'],network:['retry'],model_error:['retry'],restart:['retry'],stopped:['retry'],disposed:['retry'],answer_truncated:['retry']};
    const exchanges=new Map(),nodes=new Map();let applyBusy=false,model=null,armedClear=0,pendingFrame=0;
    const section=document.createElement('section');section.className='assistant';section.id='assistant';section.setAttribute('aria-labelledby','assistant-title');
    section.innerHTML='<div class="choice-bar" id="choice-bar"><div class="choice-text"><span class="label">Your choice</span><p id="choice-applied"></p><p id="choice-preview" class="preview-flag" hidden></p><p id="choice-result" class="small" hidden></p><p id="choice-blocked" class="small warning" hidden></p></div><div class="choice-action"></div></div>'+
      '<div class="assistant-head"><h2 id="assistant-title">Explanation</h2><span class="model-info"><span id="model-badge" class="small"></span> <button type="button" id="change-model" class="link-button">Change model</button></span></div>'+
      '<p id="assistant-notice" class="small" hidden></p><div class="assistant-recover" id="assistant-recover" hidden><button type="button" id="assistant-reload">Reread state</button></div>'+
      '<div id="thread" class="thread" role="log" aria-live="off" aria-label="Explanations and answers for this activity" tabindex="0"><p class="thread-empty small" id="thread-empty">No explanation for this activity. Apply a choice or ask a question.</p></div>'+
      '<button type="button" id="new-reply" class="new-reply" hidden>New response ↓</button>'+
      '<p id="history-note" class="small" hidden>Only the '+HISTORY+' recent exchanges for this activity are sent to the model; earlier exchanges remain here.</p>'+
      '<p id="assistant-live" class="visually-hidden" role="status" aria-live="polite"></p>'+
      '<form id="ask-form" class="ask-form" novalidate><label for="question" class="ask-label">A question about this step?</label><p id="question-context" class="question-context"></p>'+
      '<div class="shortcuts" role="group" aria-label="Quick questions"><button type="button" data-shortcut="simple">Explain more simply</button><button type="button" data-shortcut="why">Why this result?</button><button type="button" data-shortcut="compare">Compare with my previous choice</button></div>'+
      '<textarea id="question" rows="3" aria-describedby="question-context question-help"></textarea>'+
      '<div class="ask-actions"><span id="question-help" class="small">Enter to send · Shift+Enter for a new line</span><label class="junior"><input type="checkbox" id="junior"> Junior mode</label><button type="button" id="stop" hidden>Stop response</button><button type="submit" id="send" class="primary">Send</button></div></form>'+
      '<p class="small assistant-foot">Text generated through GitHub Copilot from context reread by the engine. Official numbers are those displayed by the interface. <button type="button" id="clear-conversation" class="link-button">Clear conversation</button></p>';
    $('content').after(section);
    section.querySelector('.choice-action').append($('apply-exercise'));
    const apply=$('apply-exercise'),thread=$('thread'),question=$('question'),live=$('assistant-live');
    apply.textContent='Apply and explain';
    const junior=$('junior');try{junior.checked=localStorage.getItem('osml-junior')!=='0'}catch(_){junior.checked=true}
    junior.onchange=()=>{try{localStorage.setItem('osml-junior',junior.checked?'1':'0')}catch(_){}};
    const project=()=>osml.bundle().project.id,draftKey=()=>'osml-question-draft:'+project();
    // Question drafts survive refreshes and panel reopening.
    const saved=(vscode.getState()||{}).questions||{};let draft=saved[project()];try{if(draft==null)draft=localStorage.getItem(draftKey())||''}catch(_){draft=draft||''}
    question.value=draft||'';
    const keepDraft=()=>{const all={...((vscode.getState()||{}).questions||{}),[project()]:question.value};vscode.setState({...(vscode.getState()||{}),questions:all});try{localStorage.setItem(draftKey(),question.value)}catch(_){}};
    question.addEventListener('input',()=>{keepDraft();updateForm();});
    question.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('ask-form').requestSubmit();}});
    const announce=text=>{live.textContent='';setTimeout(()=>{live.textContent=text},30);};
    const notice=(text,recover)=>{$('assistant-notice').textContent=text||'';$('assistant-notice').hidden=!text;$('assistant-recover').hidden=!recover;};
    const activity=()=>osml.state().activity;
    const spec=()=>osml.choiceFor(activity());
    const keyOf=()=>spec()?.key||null;
    const appliedValue=k=>current?.application?.answers?.[k];
    const previewValue=k=>osml.state().answers[k];
    const label=(k,v)=>osml.label(k,v);
    const blockedBy=()=>current?.blocked?.[activity()]||null;
    const generatingEntry=()=>[...exchanges.values()].find(x=>x.status==='pending'||x.status==='streaming');
    function subject(){
      const k=keyOf(),a=appliedValue(k),p=previewValue(k);
      if(k&&p!==undefined&&p!==a)return {subject:'preview',value:p,text:'Question about preview: '+label(k,p)+' — not applied'};
      if(k&&a!==undefined)return {subject:'applied',value:a,text:'Question about the applied choice: '+label(k,a)};
      return {subject:'step',text:'Question about activity « '+osml.content(activity()).title+' »'};
    }
    function renderChoice(){
      const k=keyOf();$('choice-bar').hidden=!k;if(!k)return;
      const a=appliedValue(k),p=previewValue(k),differs=p!==undefined&&p!==a,lock=blockedBy();
      $('choice-applied').textContent=a!==undefined?'Applied choice: '+label(k,a):'No applied choice for this activity.';
      $('choice-preview').hidden=!differs;$('choice-preview').textContent=differs?'Preview — choice not applied: '+label(k,p):'';
      const bound=a!==undefined?(current?.application?.results||[]).find(r=>r.key===k):null;
      $('choice-result').hidden=!bound;
      const defs=osml.bundle().results.metric_definitions;
      if(bound)$('choice-result').textContent=bound.kind==='precomputed_selection'?'Engine-attested result for '+label(k,a)+' : '+Object.keys(defs).filter(m=>m in bound.display).map(m=>defs[m].label+' '+bound.display[m]).join(' · ')+(bound.status!=='available'?' · result '+(bound.status==='stale'?'stale':bound.status):'')+'.':bound.message;
      $('choice-blocked').hidden=!lock;$('choice-blocked').textContent=lock?'Application blocked: first confirm '+lock.join(', ')+'.':'';
      const saving=busy||Boolean(queued)||Boolean(inflight);
      apply.disabled=!differs||applyBusy||conflict||!ready||Boolean(lock);
      apply.textContent=applyBusy?'Saving…':'Apply and explain';
      apply.setAttribute('aria-busy',String(applyBusy||saving));
      apply.title=lock?'Activity blocked.':p===undefined?'Choose an option first.':!differs?'This choice is already applied.':'';
    }
    function updateForm(){
      const s=subject();$('question-context').textContent=s.text;
      const active=generatingEntry(),length=question.value.length,over=length>LIMIT;
      $('send').disabled=Boolean(active)||!ready||!question.value.trim()||over;
      $('stop').hidden=!active;
      section.querySelectorAll('[data-shortcut]').forEach(b=>{b.disabled=Boolean(active)||!ready;b.hidden=b.dataset.shortcut==='compare'&&!keyOf();});
      $('question-help').textContent=over?'Limite de '+LIMIT+' character limit exceeded ('+length+'): shorten the question to keep context focused.':'Enter to send · Shift+Enter for a new line'+(length>LIMIT*0.8?' · '+length+' / '+LIMIT:'');
      $('question-help').classList.toggle('warning',over);
    }
    function about(x){
      const c=x.choice;
      if(x.kind==='chat')return 'Message du chat Copilot · '+(x.subject==='applied'?'attached to the applied choice'+(c?.label?' : '+c.label:''):'not attached to a result');
      if(x.kind==='initial')return 'Explanation of the applied choice: '+(c?.label||'');
      if(x.subject==='preview')return 'Question about preview: '+(c?.label||'')+' — not applied';
      if(x.subject==='applied')return 'Question about the applied choice: '+(c?.label||'');
      return 'Question about the activity';
    }
    function stateText(x){
      if(x.status==='pending')return x.kind==='initial'?'Preparing the explanation…':'Preparing the response…';
      if(x.status==='streaming')return 'Response in progress…';
      if(x.status==='interrupted')return 'Incomplete response — '+(x.error_message||'interrupted.');
      if(x.status==='cancelled')return 'Response stopped — '+(x.error_message||'');
      if(x.status==='error')return 'Explanation indisponible — '+(x.error_message||'model error.')+' Your choice and its results are preserved.';
      return '';
    }
    function onAction(e){
      const b=e.target.closest('button[data-action]');if(!b)return;
      b.disabled=true;
      (async()=>{
        try{
          if(b.dataset.action==='choose'){const r=await host('choose-model',{},180000);model=r.model;showModel();}
          const r=await host('retry',{exchangeId:b.dataset.exchange},20000);upsert(r.exchange);refresh(true);
        }catch(err){notice(err.message,conflictCodes.has(err.code));b.disabled=false;}
      })();
    }
    function draw(x){
      let node=nodes.get(x.exchange_id);
      if(!node){
        node=document.createElement('article');node.className='exchange';node.dataset.exchange=x.exchange_id;
        node.innerHTML='<p class="exchange-about"></p><p class="exchange-question"></p><div class="exchange-body"></div><p class="exchange-state small"></p><div class="exchange-actions"></div><p class="exchange-meta small"></p>';
        node.querySelector('.exchange-actions').addEventListener('click',onAction);nodes.set(x.exchange_id,node);
      }
      const signature=[x.status,x.answer?.length,x.current,x.error_code,x.model?.name].join('|');
      node.dataset.status=x.status;node.dataset.current=String(Boolean(x.current));node.dataset.kind=x.kind;
      if(node.dataset.signature===signature)return node;
      node.dataset.signature=signature;
      node.querySelector('.exchange-about').textContent=about(x)+(x.current||x.subject==='unattached'?'':' · concerns a previous choice');
      const q=node.querySelector('.exchange-question');q.hidden=!x.question;q.textContent=x.question?'Your question: '+x.question:'';
      const body=node.querySelector('.exchange-body');body.setAttribute('aria-busy',String(x.status==='pending'||x.status==='streaming'));
      window.osmlMarkdown.render(body,x.answer||'');
      const st=node.querySelector('.exchange-state');st.textContent=stateText(x);st.hidden=!st.textContent;
      const actions=node.querySelector('.exchange-actions');actions.replaceChildren();
      if(['error','interrupted','cancelled'].includes(x.status)&&x.current&&x.kind!=='chat'){
        for(const action of MODEL_ACTIONS[x.error_code]||(['superseded','cleared','project_switch'].includes(x.error_code)?[]:['retry'])){
          const b=document.createElement('button');b.type='button';b.dataset.action=action;b.dataset.exchange=x.exchange_id;b.textContent=action==='retry'?'Retry':'Choisir un model';actions.append(b);
        }
      }
      actions.hidden=!actions.children.length;
      const meta=node.querySelector('.exchange-meta');
      meta.textContent=x.kind==='chat'?'Published from Copilot chat; does not replace panel answers.':x.model?.name?'Generated by '+x.model.name+' via GitHub Copilot'+(x.status==='completed'?'':' · texte partiel'):'';
      meta.hidden=!meta.textContent;
      return node;
    }
    const atBottom=()=>thread.scrollHeight-thread.scrollTop-thread.clientHeight<32;
    function renderThread(grew){
      const stick=atBottom(),here=activity();
      const visible=[...exchanges.values()].filter(x=>x.activity===here||x.activity===null||x.activity===undefined).sort((a,b)=>(a.seq??1e12)-(b.seq??1e12));
      const latestCurrent=[...visible].reverse().find(x=>x.kind==='initial'&&x.current);
      const wanted=visible.map(draw);
      for(const node of wanted)node.classList.toggle('is-current',node.dataset.exchange===latestCurrent?.exchange_id);
      [...thread.querySelectorAll('.exchange')].forEach(n=>{if(!wanted.includes(n))n.remove()});
      let anchor=$('thread-empty');
      for(const node of wanted){if(anchor.nextElementSibling!==node)anchor.after(node);anchor=node;}
      $('thread-empty').hidden=wanted.length>0;
      if(grew){if(stick)thread.scrollTop=thread.scrollHeight;else $('new-reply').hidden=false;}
      $('history-note').hidden=visible.filter(x=>x.status==='completed').length<=HISTORY;
    }
    function refresh(grew){if(!osml.bundle())return;renderChoice();renderThread(grew);updateForm();}
    function upsert(x,{keepText}={}){
      const prior=exchanges.get(x.exchange_id);
      const alive=prior&&(prior.status==='pending'||prior.status==='streaming')&&(x.status==='pending'||x.status==='streaming');
      exchanges.set(x.exchange_id,{...prior,...x,answer:alive||keepText?(prior?.answer||''):x.answer??prior?.answer??'',current:x.current??prior?.current??true});
    }
    function syncConversation(data){
      const seen=new Set();
      for(const x of data.conversation||[]){seen.add(x.exchange_id);upsert(x);}
      // An in-progress response may precede its appearance in'state relu : elle n'is not removed.
      for(const [id,x] of exchanges)if(!seen.has(id)&&x.status!=='pending'&&x.status!=='streaming'){exchanges.delete(id);nodes.delete(id);}
      refresh(false);
    }
    listeners.add(message=>{
      if(message.event==='started'){upsert({...message.exchange,current:true});announce(stateText({...message.exchange,status:'pending'}));refresh(true);}
      else if(message.event==='model'){model=message.model;showModel();}
      else if(message.event==='streaming'){const x=exchanges.get(message.exchangeId);if(x&&x.status==='pending'){x.status='streaming';x.model=message.model;refresh(false);}}
      else if(message.event==='delta'){
        const x=exchanges.get(message.exchangeId);
        // Un fragment tardif d'a closed or unknown response is ignored.
        if(!x||!(x.status==='pending'||x.status==='streaming'))return;
        x.status='streaming';x.answer=(x.answer||'')+message.text;
        if(!pendingFrame)pendingFrame=requestAnimationFrame(()=>{pendingFrame=0;refresh(true);});
      }
      else if(message.event==='finished'){
        upsert({...message.exchange,current:message.current});const x=exchanges.get(message.exchange.exchange_id);
        announce(x.status==='completed'?'Response complete.':stateText(x));refresh(true);
      }
      else if(message.event==='refresh'&&ready&&!busy&&!queued&&!inflight)rpc({action:'status'}).then(data=>{if(stable(shape(data.state))===last){display(data);osml.render();}}).catch(()=>{});
    });
    function showModel(){$('model-badge').textContent=model?.name?'Model : '+model.name+' · GitHub Copilot':'Model: chosen for the first explanation';}
    async function connected(){
      try{
        const info=await host('info',{});model=info.model;showModel();
        // Resumption displays the ongoing response without sending another request.
        for(const s of info.streaming||[]){const x=exchanges.get(s.exchangeId);if(x){x.answer=s.text;x.status='streaming';}}
        if(info.projects?.length>1){
          const holder=$('project-switch');holder.replaceChildren();
          const select=document.createElement('select');select.setAttribute('aria-label','Companion project');
          for(const p of info.projects){const o=document.createElement('option');o.value=p.id;o.textContent=p.title+(p.error?' (configuration invalid)':'');o.disabled=Boolean(p.error);o.selected=p.id===project();select.append(o);}
          select.onchange=()=>{select.disabled=true;vscode.postMessage({type:'switch-project',id:select.value});};
          holder.append(select);
        }
        refresh(false);
      }catch(e){$('model-badge').textContent='Model : state indisponible';}
    }
    async function settle(){
      for(let i=0;i<120;i++){
        if(conflict)throw Object.assign(Error('Shared state changed.'),{code:'stale_revision'});
        if(!busy&&!queued&&!inflight)return;
        await new Promise(r=>setTimeout(r,100));
      }
      throw Object.assign(Error('Recording not confirmed.'),{code:'timeout'});
    }
    async function applyAndExplain(){
      const k=keyOf();if(applyBusy||!k||conflict||blockedBy())return;
      applyBusy=true;notice('');refresh(false);
      try{
        await settle();
        if(!current.pending_event_id||previewValue(k)===appliedValue(k)){announce('This choice is already applied.');return;}
        const ack=await host('apply-explain',{eventId:current.pending_event_id,expectedRevision:current.revision,contextHash:current.context_hash,activity:activity(),key:k,junior:junior.checked},20000);
        // The attested result appears before the explanation finishes.
        display(ack.snapshot);osml.render();if(ack.exchange)upsert(ack.exchange,{keepText:true});
        sync.textContent='Choice applied in the exercise. No project decision changed.';bar.dataset.sync='saved';
        announce('Applied choice: '+label(k,appliedValue(k))+'. Preparing the explanation…');
      }catch(e){
        if(conflictCodes.has(e.code)){conflict=true;bar.dataset.sync='conflict';notice('Shared state changed: no explanation requested. Reread state before continuing.',true);}
        else if(e.code==='timeout'){bar.dataset.sync='offline';notice('Application uncertain: the engine did not confirm. Reread state before retrying; no explanation requested.',true);}
        else notice('Choice not applied: '+e.message+' No explanation requested.',true);
        announce('Choice not applied.');
      }finally{applyBusy=false;refresh(false);}
    }
    $('assistant-reload').onclick=async()=>{notice('');await load();if(!conflict)$('assistant-recover').hidden=true;};
    async function send(text,options={}){
      if(!ready||generatingEntry()||!text.trim())return false;
      if(text.length>LIMIT){updateForm();return false;}
      const s=subject(),k=keyOf();
      const exchangeId='q-'+crypto.randomUUID().replaceAll('-','');
      const payload={exchangeId,question:text,activity:activity(),subject:s.subject,contextHash:current.context_hash,junior:junior.checked,comparePrevious:Boolean(options.compare),expectedApplicationEventId:current.application?.event_id??null};
      if(s.subject==='preview')payload.previewValue=s.value;
      upsert({exchange_id:exchangeId,kind:'question',status:'pending',activity:activity(),subject:s.subject,question:text,answer:'',choice:s.subject==='step'?null:{key:k,value:s.value,label:label(k,s.value)},current:true});
      refresh(true);
      try{const ack=await host('ask',payload,20000);upsert(ack.exchange);refresh(false);return true;}
      catch(e){
        exchanges.delete(exchangeId);nodes.get(exchangeId)?.remove();nodes.delete(exchangeId);
        notice(e.code==='stale_context'||e.code==='context'?'The applied choice changed: reread state and ask again.':'Question not sent: '+e.message,conflictCodes.has(e.code));
        refresh(false);return false;
      }
    }
    $('ask-form').addEventListener('submit',async e=>{
      e.preventDefault();const text=question.value;
      if(await send(text)&&question.value===text){question.value='';keepDraft();updateForm();}
    });
    const shortcuts={simple:'Explain more simply.',why:'Why this result?',compare:'Compare with my previous choice.'};
    section.querySelectorAll('[data-shortcut]').forEach(b=>b.onclick=()=>send(shortcuts[b.dataset.shortcut],{compare:b.dataset.shortcut==='compare'}));
    $('stop').onclick=()=>{const x=generatingEntry();if(x)host('stop',{exchangeId:x.exchange_id}).catch(e=>notice(e.message));};
    $('change-model').onclick=async()=>{try{const r=await host('choose-model',{},180000);model=r.model;showModel();announce('Model choisi : '+model.name);}catch(e){notice(e.message);}};
    $('new-reply').onclick=()=>{thread.scrollTop=thread.scrollHeight;$('new-reply').hidden=true;};
    thread.addEventListener('scroll',()=>{if(atBottom())$('new-reply').hidden=true;});
    $('clear-conversation').onclick=async()=>{
      const b=$('clear-conversation');
      if(Date.now()-armedClear>6000){armedClear=Date.now();b.textContent='Confirm: clear questions and answers for this project (retain choices, results, confirmations, and other projects)';return;}
      armedClear=0;b.textContent='Clear conversation';
      try{const data=await host('clear',{confirm:true});exchanges.clear();nodes.clear();display(data);announce('Conversation cleared. Choices and results are retained.');}catch(e){notice(e.message);}
    };
    osml.canAsk=true;
    osml.onClarify=text=>send(text);
    osml.afterRender=()=>refresh(false);
    showModel();
    return {sync:syncConversation,refresh:()=>refresh(false),connected,applying:()=>applyBusy,applyAndExplain};
  }
})();
