/* ---------------- Theme (palette + light/dark) ---------------- */
function setTheme(t, persist){
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('modeToggle').setAttribute('aria-pressed', t==='dark'?'true':'false');
  if(persist!==false) localStorage.setItem('conboart-theme', t);
}
function setPalette(p, persist){
  document.documentElement.setAttribute('data-palette', p);
  document.querySelectorAll('.swatch').forEach(b=>b.setAttribute('aria-pressed', b.dataset.palette===p?'true':'false'));
  if(persist!==false) localStorage.setItem('conboart-palette', p);
}
document.getElementById('modeToggle').addEventListener('click',()=>{
  setTheme(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark');
});
document.querySelectorAll('.swatch').forEach(b=>{
  b.addEventListener('click',()=>setPalette(b.dataset.palette));
});
// sync control UI to whatever the early inline script already applied (no re-write to storage)
setTheme(document.documentElement.getAttribute('data-theme')||'light', false);
setPalette(document.documentElement.getAttribute('data-palette')||'heritage', false);
