/* ---------------- Generate ---------------- */
const statuses=['Reconstructing geometry…','Building the mesh…','Running printability check…','Almost there…'];
let genAbortController=null;

// Status badge shown top-left on other tabs while away from Upload, so
// leaving to check About/FAQs doesn't need a confirm-to-leave warning.
function updateGenStatusBadge(activePage){
  const badge=document.getElementById('genStatusBadge');
  const text=document.getElementById('genStatusText');
  const onUpload=activePage ? activePage==='upload' : document.getElementById('page-upload').classList.contains('active');
  let status='none', label='Status: none';
  if(state.jobActive){ status='generating'; label='Status: generating'; }
  else if(state.hasModel){ status='done'; label='Status: done'; }
  badge.className='gen-status-badge'+(status!=='none'?' '+status:'');
  text.textContent=label;
  badge.style.display=onUpload?'none':'flex';
}

function fileToDataURL(file){
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(reader.result);
    reader.onerror=reject;
    reader.readAsDataURL(file);
  });
}

async function buildImagesPayload(){
  if(state.mode==='multi'){
    const entries=[];
    for(const slot of MULTI_SLOTS){
      const f=state.files[slot];
      if(!f) continue;
      const dataUrl=await fileToDataURL(f);
      entries.push({image_base64:dataUrl, mime:f.type||'image/png', slot});
    }
    return entries;
  }
  const dataUrl=await fileToDataURL(state.file);
  return [{image_base64:dataUrl, mime:state.file.type||'image/png', slot:'front'}];
}

async function startGenerate(){
  const hasInput=state.mode==='multi' ? !!state.files.front : !!state.file;
  if(state.jobActive || !hasInput) return;   // one active job per session
  state.jobActive=true;
  updateGenStatusBadge();
  genBtn.disabled=true;
  showView('loading');
  const el=document.getElementById('genStatus');
  let i=0; el.textContent=statuses[0];
  const iv=setInterval(()=>{ i=(i+1)%statuses.length; el.textContent=statuses[i]; },1400);
  genAbortController=new AbortController();

  try{
    const images=await buildImagesPayload();
    const r=await fetch('/api/generate',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({images}),
      signal:genAbortController.signal
    });
    if(!r.ok) throw new Error(await apiErrorMessage(r));
    const data=await r.json();

    state.jobId=data.job_id;
    applyInfo(data.info);
    renderPrintability(data.report);

    let buf=null;
    try{ buf=await fetchModelBlob(state.jobId); }catch(e){ console.error(e); }
    modelBuffer=buf;
    if(viewerReady && modelBuffer) loadMeshFromBuffer(modelBuffer);

    clearInterval(iv);
    state.jobActive=false;
    genBtn.disabled=false;
    state.hasModel=true;
    updateGenStatusBadge();
    showView('viewer');
    updateInfoPanel();
  }catch(e){
    clearInterval(iv);
    state.jobActive=false;
    genBtn.disabled=false;
    updateGenStatusBadge();
    if(e.name==='AbortError'){
      toast('Generation cancelled');
    }else{
      toast('Generation failed: '+e.message);
    }
    showView('drop');
  }
}

function cancelGenerate(){
  if(!state.jobActive || !genAbortController) return;
  genAbortController.abort(); // stops our wait; the AbortError path in startGenerate() resets state
}

function retryGenerate(){
  const hasInput=state.mode==='multi' ? !!state.files.front : !!state.file;
  if(state.jobActive || !hasInput) return;
  startGenerate(); // re-submits the same image(s) (or cropped selection, in single mode) as a fresh job
}

function renderPrintability(report){
  state.verdict=report.verdict;
  const v=verdictInfo(report.verdict);
  const badge=document.getElementById('pBadge');
  const verdict=document.getElementById('pVerdict');
  badge.className='print-badge '+v.cls;
  badge.textContent=v.mark;
  verdict.className='print-verdict'+(v.cls==='ok'?' ok':'');
  verdict.textContent=v.headline;
  renderPrintabilitySummary();

  const labels={
    watertight:'Watertight — no holes',
    consistent_normals:'Consistent surface normals',
    single_body:'Single connected body',
    positive_volume:'Valid, positive volume'
  };
  const ul=document.getElementById('pChecks');
  ul.innerHTML='';
  for(const key of ['watertight','consistent_normals','single_body','positive_volume']){
    const ok=!!report.checks[key];
    const li=document.createElement('li');
    li.innerHTML='<span class="mk" style="color:'+(ok?'var(--green)':'var(--red)')+'">'+(ok?'✓':'✕')+'</span> '+labels[key];
    ul.appendChild(li);
  }
}

function renderPrintabilitySummary(){
  const el=document.getElementById('sPrint');
  if(!state.verdict){ el.textContent='—'; el.style.color=''; return; }
  const v=verdictInfo(state.verdict);
  el.textContent=v.summary;
  el.style.color=v.color;
}

/* Converts native-unit dims/volume to target mm scale */
function computeScaledStats(target){
  const dims=(state.nativeDims&&state.nativeDims.length===3)?state.nativeDims:null;
  if(!dims) return {dims:null, vol:null};
  const longest=Math.max(...dims);
  if(!(longest>0)) return {dims:null, vol:null};
  const factor=target/longest;
  const vol=typeof state.nativeVolume==='number'?state.nativeVolume:null;
  return {
    dims:dims.map(d=>+(d*factor).toFixed(1)),
    // native units³ → mm³ → cm³
    vol:vol===null?null:+(vol*Math.pow(factor,3)/1000).toFixed(2)
  };
}

function updateInfoPanel(){
  const label={S:'Small',M:'Medium',L:'Large'}[state.size];
  const {dims,vol}=computeScaledStats(state.mm);
  const dimStr=dims?dims.join(' × ')+' mm':'—';
  document.getElementById('iDim').textContent=dimStr;
  document.getElementById('stageScale').textContent=label+' · '+state.mm+' mm';
  document.getElementById('iVol').textContent=vol===null?'—':vol+' cm³';
  document.getElementById('iTri').textContent=
    typeof state.triangles==='number'?state.triangles.toLocaleString():'—';
  document.getElementById('sSize').textContent=label+' · '+state.mm+' mm';
  document.getElementById('sDim').textContent=dimStr;
  renderPrintabilitySummary();
}

/* ---------------- Scale ---------------- */
document.querySelectorAll('#scale button').forEach(b=>{
  b.addEventListener('click',()=>{
    if(b.classList.contains('on')) return;
    document.querySelectorAll('#scale button').forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    state.size=b.dataset.size; state.mm=+b.dataset.mm;
    updateInfoPanel();
    applyPreviewScale(); // live viewer rescale; the backend only bakes scale at export
  });
});

/* ---------------- Clean up ---------------- */
async function cleanUp(){
  if(!state.jobId) return;
  const btn=document.getElementById('cleanBtn');
  btn.disabled=true; btn.textContent='Cleaning up…';
  try{
    const r=await fetch(`/api/cleanup/${state.jobId}`,{method:'POST'});
    if(!r.ok) throw new Error(await apiErrorMessage(r));
    const data=await r.json();
    applyInfo(data.info);
    renderPrintability(data.report);
    updateInfoPanel();
    try{
      const buf=await fetchModelBlob(state.jobId);
      modelBuffer=buf;
      if(viewerReady) loadMeshFromBuffer(buf);
    }catch(e){ console.error(e); }
    btn.textContent='Cleaned ✓';
    if(data.unprintable){
      alert('This image could not generate a proper printable model. Try a different image or angle.');
    }else{
      toast('Model cleaned · printability re-checked');
    }
  }catch(e){
    btn.textContent='Clean up model';
    toast('Cleanup failed: '+e.message);
  }finally{
    setTimeout(()=>{ btn.disabled=false; btn.textContent='Clean up model'; },1400);
  }
}
