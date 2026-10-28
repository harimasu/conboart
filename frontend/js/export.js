/* ---------------- Export modal ---------------- */
function openExportModal(){
  document.getElementById('mSize').textContent={S:'Small',M:'Medium',L:'Large'}[state.size]+' · '+state.mm+' mm';
  const warn=document.getElementById('mWarn');
  const v=verdictInfo(state.verdict);
  const mPrint=document.getElementById('mPrint');
  mPrint.textContent=state.verdict?v.summary:'—';
  mPrint.style.color=state.verdict?v.color:'';
  // Anything short of a clean pass gets the heads-up, warnings included.
  warn.style.display=state.verdict==='ok'?'none':'block';
  document.getElementById('overlay').classList.add('show');
}
function closeModal(){document.getElementById('overlay').classList.remove('show');}
function confirmExport(){closeModal();showView('export');fmtNote();}
document.getElementById('overlay').addEventListener('click',e=>{if(e.target.id==='overlay')closeModal();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeModal();closeCropModal();}});

/* ---------------- File name ---------------- */
const DEFAULT_EXPORT_NAME='conboart_model';
function exportName(fmt){
  let name=document.getElementById('fname').value.trim();
  name=name.replace(/[\\/:*?"<>|\x00-\x1f]/g,'').replace(new RegExp('\\.'+fmt+'$','i'),'').replace(/^\.+|\.+$/g,'').trim();
  return (name||DEFAULT_EXPORT_NAME)+'.'+fmt;
}

/* ---------------- Format note + download ---------------- */
function fmtNote(){
  const sel=document.getElementById('fmt');
  const opt=sel.options[sel.selectedIndex];
  document.getElementById('fmtNote').textContent=opt.dataset.note||'';
  document.getElementById('sFile').textContent=exportName(sel.value);
  document.getElementById('dlStatus').style.display='none';
}
async function downloadFile(){
  if(!state.jobId) return;
  const sel=document.getElementById('fmt');
  const fmt=sel.value;
  const dlBtn=document.getElementById('dlBtn');
  const dlStatus=document.getElementById('dlStatus');
  dlStatus.style.display='none';
  dlBtn.disabled=true; dlBtn.textContent='Preparing…';
  try{
    const r=await fetch(`/api/convert/${state.jobId}?format=${encodeURIComponent(fmt)}&scale=${encodeURIComponent(state.size)}`);
    if(!r.ok) throw new Error(await apiErrorMessage(r));
    const blob=await r.blob();
    const filename=exportName(fmt);
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a'); a.href=url; a.download=filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    dlStatus.textContent=`Saved ${filename} — pick another format to export again.`;
    dlStatus.style.display='block';
  }catch(e){
    toast('Export failed: '+e.message);
  }finally{
    dlBtn.disabled=false; dlBtn.textContent='Download';
  }
}
function resetForNewUpload(){
  // clear file + model state and return to the upload step (same mode as before)
  clearFile();
  MULTI_SLOTS.forEach(clearMultiFile);
  state.hasModel=false; state.jobActive=false; state.size='M'; state.mm=70;
  state.jobId=null; state.nativeDims=null; state.nativeVolume=null;
  state.triangles=null; state.verdict=null;
  modelBuffer=null;
  previewCenterXZ=null; previewMinY=null; previewMaxDim=null;
  resetOrbitStandard();
  updateInfoPanel();
  if(mesh){ scene.remove(mesh); mesh=null; }
  document.querySelectorAll('#scale button').forEach(x=>x.classList.toggle('on', x.dataset.size==='M'));
  document.getElementById('dlStatus').style.display='none';
  document.getElementById('fname').value='';
  updateGenStatusBadge();
  showView('drop');
}
