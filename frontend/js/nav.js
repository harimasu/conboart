/* ---------------- Routing ---------------- */
const pages = ['upload','about','faqs'];
function go(p){
  pages.forEach(x=>{
    document.getElementById('page-'+x).classList.toggle('active', x===p);
    const nav=document.querySelector('.nlink[data-nav="'+x+'"]');
    if(nav) nav.setAttribute('aria-current', x===p?'page':'false');
  });
  window.scrollTo({top:0,behavior:'smooth'});
  if(p==='upload' && !state.hasModel && !state.jobActive && curView!=='mode' && curView!=='drop') showView('mode');
  // The viewer's canvas can get initialized (or a completed generation can
  // land) while #page-upload is display:none — eg. generation finishes
  // while on another tab — leaving it sized 0x0 with nothing to ever fix it.
  // Resize once the container is actually visible again.
  if(p==='upload' && curView==='viewer' && viewerReady){ onResize(); renderer.render(scene,camera); }
  updateGenStatusBadge(p);
}

/* ---------------- Upload views ---------------- */
let curView='intro';
const views=['intro','mode','drop','loading','viewer','export','empty'];
const STEPS=[
  {view:'mode', n:'01', title:'Choose mode', desc:'Single photo, or several angles for accuracy.'},
  {view:'drop', n:'02', title:'Upload', desc:'Drop in a clear photo of your subject.'},
  {view:'viewer', n:'03', title:'Review &amp; size', desc:'Inspect the model, set S / M / L, check printability.'},
  {view:'export', n:'04', title:'Export', desc:'Download for printing or import into SketchUp.'},
];
function updateStepsBars(){
  const html=STEPS.map(s=>'<div class="step'+(s.view===curView?' current':'')+'"><div class="n">'+s.n+'</div><h3>'+s.title+'</h3><p>'+s.desc+'</p></div>').join('');
  document.querySelectorAll('.steps[data-auto]').forEach(el=>{ el.innerHTML=html; });
}
function showView(v){
  curView=v;
  views.forEach(x=>document.getElementById('v-'+x).classList.toggle('active', x===v));
  if(v==='viewer'){ ensureViewer(); }
  updateStepsBars();
  window.scrollTo({top:0,behavior:'smooth'});
}
