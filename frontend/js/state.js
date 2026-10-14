/* ---------------- Shared app state + small helpers ---------------- */

// nativeDims/nativeVolume are in the mesh's own units, not mm — the scale is
// baked at export, so the client converts for display. Null until a real model
// arrives; nothing here is a stand-in number.
const state={
  mode:'single', file:null, files:{}, size:'M', mm:100, verdict:null, hasModel:false, jobActive:false,
  jobId:null, nativeDims:null, nativeVolume:null, triangles:null
};

const VERDICT={
  ok:  {summary:'Ready ✓',            headline:'Ready to print',    mark:'✓', cls:'ok',   color:'var(--green)'},
  warn:{summary:'May need attention', headline:'May need attention',mark:'!', cls:'warn', color:'var(--brick)'},
  fail:{summary:'Not print-ready',    headline:'Not print-ready',   mark:'✕', cls:'fail', color:'var(--red)'}
};
function verdictInfo(v){ return VERDICT[v] || VERDICT.fail; }

function applyInfo(info){
  info=info||{};
  state.nativeDims=Array.isArray(info.dimensions)?info.dimensions:null;
  state.nativeVolume=typeof info.volume==='number'?info.volume:null;
  state.triangles=typeof info.triangles==='number'?info.triangles:null;
}

async function apiErrorMessage(r){
  try{ const j=await r.json(); return j.detail || JSON.stringify(j); }
  catch(e){ return r.statusText || ('HTTP '+r.status); }
}

/* ---------------- Toast ---------------- */
let tt;
function toast(m){
  const el=document.getElementById('toast');
  el.textContent=m; el.classList.add('show');
  clearTimeout(tt); tt=setTimeout(()=>el.classList.remove('show'),2200);
}
