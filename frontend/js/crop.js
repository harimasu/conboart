/* ---------------- Select area (crop before generating) ---------------- */
// Lets the user box out just the subject before it's sent for generation,
// so the model isn't guessing from background clutter or unwanted parts.
let cropImg=null, cropDisplayScale=1, cropRect=null, cropDragging=false, cropStart=null;

async function openCropModal(){
  if(!state.file){ toast('Upload an image first'); return; }
  const url=URL.createObjectURL(state.file);
  const img=new Image();
  try{
    await new Promise((resolve,reject)=>{ img.onload=resolve; img.onerror=reject; img.src=url; });
  }catch(e){ toast('Could not open that image for selection'); return; }
  URL.revokeObjectURL(url);
  cropImg=img;
  fitCropCanvas();
  document.getElementById('cropOverlay').classList.add('show');
}
function closeCropModal(){
  document.getElementById('cropOverlay').classList.remove('show');
}
// Sizes the canvas to fit whatever image + whatever viewport, matching the
// same box .modal-crop/#cropCanvas's CSS constrains itself to (see style.css)
// so the internal resolution isn't blurrier or wastefully bigger than shown.
function fitCropCanvas(){
  if(!cropImg) return;
  const canvas=document.getElementById('cropCanvas');
  const maxW=Math.min(window.innerWidth*0.92,760)-56; // .modal-crop width minus its padding
  const maxH=window.innerHeight*0.6;
  const scale=Math.min(1, maxW/cropImg.naturalWidth, maxH/cropImg.naturalHeight);
  canvas.width=Math.max(1,Math.round(cropImg.naturalWidth*scale));
  canvas.height=Math.max(1,Math.round(cropImg.naturalHeight*scale));
  cropDisplayScale=cropImg.naturalWidth/canvas.width; // native px per display px
  cropRect=null;
  document.getElementById('cropConfirmBtn').disabled=true;
  drawCrop();
}
window.addEventListener('resize',()=>{
  if(document.getElementById('cropOverlay').classList.contains('show')) fitCropCanvas();
});
function drawCrop(){
  const canvas=document.getElementById('cropCanvas');
  const ctx=canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.drawImage(cropImg,0,0,canvas.width,canvas.height);
  if(!cropRect) return;
  const {x,y,w,h}=cropRect;
  ctx.fillStyle='rgba(0,0,0,.55)';
  ctx.fillRect(0,0,canvas.width,y);
  ctx.fillRect(0,y+h,canvas.width,canvas.height-y-h);
  ctx.fillRect(0,y,x,h);
  ctx.fillRect(x+w,y,canvas.width-x-w,h);
  ctx.strokeStyle='#fff'; ctx.lineWidth=2;
  ctx.strokeRect(x+1,y+1,Math.max(0,w-2),Math.max(0,h-2));
}
function cropPointerPos(e){
  const canvas=document.getElementById('cropCanvas');
  const r=canvas.getBoundingClientRect();
  return {
    x:Math.max(0,Math.min(canvas.width,(e.clientX-r.left)*(canvas.width/r.width))),
    y:Math.max(0,Math.min(canvas.height,(e.clientY-r.top)*(canvas.height/r.height)))
  };
}
(function initCropCanvas(){
  const canvas=document.getElementById('cropCanvas');
  canvas.addEventListener('pointerdown',e=>{
    cropStart=cropPointerPos(e); cropDragging=true;
    canvas.setPointerCapture(e.pointerId);
    cropRect={x:cropStart.x,y:cropStart.y,w:0,h:0};
    document.getElementById('cropConfirmBtn').disabled=true;
  });
  canvas.addEventListener('pointermove',e=>{
    if(!cropDragging) return;
    const p=cropPointerPos(e);
    cropRect={
      x:Math.min(cropStart.x,p.x), y:Math.min(cropStart.y,p.y),
      w:Math.abs(p.x-cropStart.x), h:Math.abs(p.y-cropStart.y)
    };
    drawCrop();
  });
  canvas.addEventListener('pointerup',()=>{
    cropDragging=false;
    const big=cropRect && cropRect.w>8 && cropRect.h>8;
    document.getElementById('cropConfirmBtn').disabled=!big;
    if(!big){ cropRect=null; drawCrop(); }
  });
})();
function resetCropSelection(){
  cropRect=null;
  document.getElementById('cropConfirmBtn').disabled=true;
  drawCrop();
}
async function confirmCrop(){
  if(!cropRect||!cropImg) return;
  const nx=Math.round(cropRect.x*cropDisplayScale);
  const ny=Math.round(cropRect.y*cropDisplayScale);
  const nw=Math.round(cropRect.w*cropDisplayScale);
  const nh=Math.round(cropRect.h*cropDisplayScale);

  const out=document.createElement('canvas');
  out.width=nw; out.height=nh;
  out.getContext('2d').drawImage(cropImg, nx, ny, nw, nh, 0, 0, nw, nh);

  const mime=state.file.type||'image/png';
  const blob=await new Promise(resolve=>out.toBlob(resolve, mime));
  const croppedFile=new File([blob], 'cropped-'+state.file.name, {type:mime});
  state.file=croppedFile;

  document.getElementById('dz-thumb').src=out.toDataURL(mime);
  document.getElementById('dz-name').textContent=croppedFile.name;
  document.getElementById('dz-meta').textContent=(croppedFile.size/1024/1024).toFixed(1)+' MB · area selected';

  closeCropModal();
  toast('Selection applied — only that area will be sent to generate');
}
document.getElementById('cropOverlay').addEventListener('click',e=>{if(e.target.id==='cropOverlay')closeCropModal();});
