/* ---------------- Three.js viewer ---------------- */
let renderer,scene,camera,mesh,viewerReady=false,modelBuffer=null;

async function fetchModelBlob(jobId){
  const r=await fetch(`/api/convert/${jobId}?format=glb&scale=${state.size}`);
  if(!r.ok) throw new Error(await apiErrorMessage(r));
  return await r.arrayBuffer();
}

function ensureViewer(){
  if(viewerReady){onResize();return;}
  // The viewer is a preview, not the product — if three.js failed to load,
  // say so and leave export working rather than throwing on every view switch.
  if(typeof THREE==='undefined'||!THREE.GLTFLoader){
    const stage=document.getElementById('stage');
    if(!stage.querySelector('.stage-fallback')){
      const p=document.createElement('p');
      p.className='stage-fallback';
      p.textContent='3D preview unavailable — the viewer library did not load. You can still size and export the model.';
      stage.appendChild(p);
    }
    return;
  }
  initViewer();
}
function initViewer(){
  const stage=document.getElementById('stage');
  const w=stage.clientWidth,h=stage.clientHeight;
  scene=new THREE.Scene();
  camera=new THREE.PerspectiveCamera(38,w/h,0.1,100);
  camera.position.set(0,0.4,5.4);
  renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.setSize(w,h);
  stage.appendChild(renderer.domElement);

  const key=new THREE.DirectionalLight(0xfff2dc,1.15); key.position.set(3,4,5); scene.add(key);
  const rim=new THREE.DirectionalLight(0xC59230,.5); rim.position.set(-4,2,-3); scene.add(rim);
  scene.add(new THREE.AmbientLight(0x6d4a3a,.55));

  if(modelBuffer){ loadMeshFromBuffer(modelBuffer); } else { addPlaceholderMesh(); }
  renderer.render(scene,camera); // paint now; no-op if modelBuffer's parse hasn't resolved yet

  addOrbit(stage);
  viewerReady=true;
  animate();
  window.addEventListener('resize',onResize);
}
function addPlaceholderMesh(){
  const geo=new THREE.TorusKnotGeometry(1.05,0.36,180,32,2,3);
  const mat=new THREE.MeshStandardMaterial({color:0xd9cdb4,roughness:.62,metalness:.12,flatShading:false});
  mesh=new THREE.Mesh(geo,mat);
  scene.add(mesh);
}
function loadMeshFromBuffer(buffer){
  const loader=new THREE.GLTFLoader();
  loader.parse(buffer.slice(0),'',(gltf)=>{
    if(mesh){ scene.remove(mesh); }
    const obj=gltf.scene;
    const box=new THREE.Box3().setFromObject(obj);
    const size=new THREE.Vector3(); box.getSize(size);
    const center=new THREE.Vector3(); box.getCenter(center);
    const maxDim=Math.max(size.x,size.y,size.z)||1;
    const scaleFactor=1.9/maxDim;
    obj.scale.setScalar(scaleFactor);
    // scale is applied before translation, so the recentering offset needs scaling too
    obj.position.copy(center).multiplyScalar(-scaleFactor);
    scene.add(obj);
    mesh=obj;
    renderer.render(scene,camera); // paint now, don't wait on the next animate() tick
  },(err)=>{
    console.error(err);
    toast('Could not load the model preview');
  });
}

let autoRot=true,rotX=0.35,rotY=0,dragging=false,lx=0,ly=0,dist=5.4;
function addOrbit(stage){
  stage.addEventListener('pointerdown',e=>{dragging=true;autoRot=false;lx=e.clientX;ly=e.clientY;stage.setPointerCapture(e.pointerId);});
  stage.addEventListener('pointermove',e=>{
    if(!dragging)return;
    rotY-=(e.clientX-lx)*0.008; rotX+=(e.clientY-ly)*0.008;
    rotX=Math.max(-1.2,Math.min(1.2,rotX));
    lx=e.clientX;ly=e.clientY;
  });
  stage.addEventListener('pointerup',()=>dragging=false);
  stage.addEventListener('pointerleave',()=>dragging=false);
  stage.addEventListener('wheel',e=>{e.preventDefault();dist=Math.max(3.2,Math.min(8.5,dist+e.deltaY*0.003));},{passive:false});
}
function animate(){
  requestAnimationFrame(animate);
  if(autoRot) rotY+=0.0045;
  if(mesh){
    camera.position.x=Math.sin(rotY)*dist;
    camera.position.z=Math.cos(rotY)*dist;
    camera.position.y=Math.sin(rotX)*dist*0.6+0.3;
    camera.lookAt(0,0,0);
  }
  renderer.render(scene,camera);
}
function onResize(){
  if(!viewerReady)return;
  const stage=document.getElementById('stage');
  const w=stage.clientWidth,h=stage.clientHeight;
  camera.aspect=w/h;camera.updateProjectionMatrix();
  renderer.setSize(w,h);
}
