/* ---------------- File handling ---------------- */
const dz=document.getElementById('dropzone');
const fileInput=document.getElementById('file');
const genBtn=document.getElementById('genBtn');
const MAX=10*1024*1024;

dz.addEventListener('click',()=>fileInput.click());
dz.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();fileInput.click();}});
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag');});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag'));
dz.addEventListener('drop',e=>{e.preventDefault();dz.classList.remove('drag');if(e.dataTransfer.files[0])handleFile(e.dataTransfer.files[0]);});
fileInput.addEventListener('change',e=>{if(e.target.files[0])handleFile(e.target.files[0]);});

function handleFile(f){
  const err=document.getElementById('dz-error');
  err.style.display='none';
  const okType=/\.(png|jpe?g)$/i.test(f.name);
  if(!okType){ showErr('That file isn’t a PNG or JPG. Try a different image.'); return; }
  if(f.size>MAX){ showErr('That file is over 10 MB. Try a smaller image.'); return; }
  state.file=f;
  const url=URL.createObjectURL(f);
  document.getElementById('dz-thumb').src=url;
  document.getElementById('dz-name').textContent=f.name;
  document.getElementById('dz-meta').textContent=(f.size/1024/1024).toFixed(1)+' MB · ready';
  document.getElementById('dz-empty').style.display='none';
  document.getElementById('dz-filled').style.display='flex';
  dz.classList.add('hasfile');
  genBtn.disabled=false;
}
function showErr(m){
  const err=document.getElementById('dz-error');
  err.textContent=m; err.style.display='block';
}
function clearFile(){
  state.file=null; fileInput.value='';
  document.getElementById('dz-empty').style.display='block';
  document.getElementById('dz-filled').style.display='none';
  dz.classList.remove('hasfile');
  genBtn.disabled=true;
}
async function loadSample(){
  const svgBlob=new Blob([sampleSVG()],{type:'image/svg+xml'});
  const url=URL.createObjectURL(svgBlob);
  const img=new Image();
  await new Promise((resolve,reject)=>{ img.onload=resolve; img.onerror=reject; img.src=url; });
  const canvas=document.createElement('canvas'); canvas.width=256; canvas.height=256;
  const ctx=canvas.getContext('2d'); ctx.drawImage(img,0,0,256,256);
  URL.revokeObjectURL(url);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
  const file=new File([blob],'sample-figurine.png',{type:'image/png'});
  state.file=file;
  document.getElementById('dz-thumb').src=canvas.toDataURL('image/png');
  document.getElementById('dz-name').textContent='sample-figurine.png';
  document.getElementById('dz-meta').textContent=(file.size/1024/1024).toFixed(1)+' MB · sample';
  document.getElementById('dz-empty').style.display='none';
  document.getElementById('dz-filled').style.display='flex';
  dz.classList.add('hasfile');
  genBtn.disabled=false;
  startGenerate();
}
function sampleSVG(){
  return '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#E8E1CC"/><circle cx="32" cy="24" r="12" fill="#9C3C20"/><rect x="20" y="34" width="24" height="24" rx="4" fill="#6D1214"/></svg>';
}

/* ---------------- Upload mode (single vs multi image) ---------------- */
function chooseUploadMode(mode){
  state.mode=mode;
  clearFile();
  clearMultiFile('front'); clearMultiFile('back'); clearMultiFile('left'); clearMultiFile('right');
  document.getElementById('dropzone').style.display=mode==='single'?'':'none';
  document.getElementById('dropzoneMulti').style.display=mode==='multi'?'block':'none';
  document.getElementById('selectAreaBtn').style.display=mode==='single'?'':'none';
  document.getElementById('sampleBtn').style.display=mode==='single'?'':'none';
  document.getElementById('dropTitle').innerHTML=mode==='single'
    ?'One photo is<br>all it takes.'
    :'A few angles make<br>a much better model.';
  document.getElementById('dzTitle').textContent=mode==='single'
    ?'Drop your image here'
    :'Drop an image here';
  document.getElementById('dzHint').textContent=mode==='single'
    ?'One clear photo works best — plain background, even lighting.'
    :'Best results: one clear subject, plain background, even lighting.';
  genBtn.disabled=true;
  showView('drop');
}

/* ---------------- Multi-image slots (front required, back/left/right optional) ---------------- */
const MULTI_SLOTS=['front','back','left','right'];
MULTI_SLOTS.forEach(slot=>{
  document.getElementById('fileMulti-'+slot).addEventListener('change',e=>{
    if(e.target.files[0]) handleMultiFile(slot, e.target.files[0]);
  });
});
function triggerMultiFile(slot){
  document.getElementById('fileMulti-'+slot).click();
}
function handleMultiFile(slot, f){
  const okType=/\.(png|jpe?g)$/i.test(f.name);
  if(!okType){ toast('That file isn’t a PNG or JPG.'); return; }
  if(f.size>MAX){ toast('That file is over 10 MB.'); return; }
  state.files[slot]=f;
  const url=URL.createObjectURL(f);
  document.getElementById('slotThumb-'+slot).src=url;
  document.getElementById('slotThumb-'+slot).style.display='block';
  document.getElementById('slotEmpty-'+slot).style.display='none';
  document.getElementById('slotBox-'+slot).classList.add('filled');
  updateMultiGenBtn();
}
function clearMultiFile(slot){
  delete state.files[slot];
  document.getElementById('fileMulti-'+slot).value='';
  document.getElementById('slotThumb-'+slot).style.display='none';
  document.getElementById('slotThumb-'+slot).src='';
  document.getElementById('slotEmpty-'+slot).style.display='block';
  document.getElementById('slotBox-'+slot).classList.remove('filled');
  updateMultiGenBtn();
}
function updateMultiGenBtn(){
  if(state.mode==='multi') genBtn.disabled=!state.files.front;
}
