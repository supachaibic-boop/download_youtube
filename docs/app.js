import * as storage from './storage.js';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={ready:'พร้อมเล่น',playing:'กำลังเล่น',paused:'หยุดชั่วคราว',ended:'เล่นจบแล้ว',error:'เล่นไม่ได้'};
const icon=id=>`<svg fill="none" stroke="currentColor" stroke-width="1.7"><use href="#${id}"/></svg>`;
let videos=[],filter='all',currentId=null,editId=null,player=null,ytPromise=null,toastTimer,loading=false,playGeneration=0,saving=Promise.resolve(),storageReady=false;
const now=()=>new Date().toISOString();
const uid=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,"0")).join("");
function toast(text){$('toast').textContent=text;$('toast').classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.add('hidden'),5000);}
export function videoId(raw){
  try{
    const p=new URL(raw.trim());if(p.protocol!=='https:'||p.username||p.password||(p.port&&p.port!=='443'))throw Error();
    let id='';if(p.hostname==='youtu.be')id=p.pathname.replace(/^\//,'');
    else if(['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'].includes(p.hostname)){
      if(p.pathname==='/watch')id=p.searchParams.get('v')||'';
      else if(/^\/(shorts|live|embed)\//.test(p.pathname))id=p.pathname.split('/')[2];
    }
    if(!/^[A-Za-z0-9_-]{11}$/.test(id))throw Error();return id;
  }catch{throw Error('กรุณาใส่ลิงก์วิดีโอ YouTube แบบ HTTPS ที่ถูกต้อง');}
}
function canonical(id){return 'https://www.youtube.com/watch?v='+id;}
function render(){
  const q=$('search').value.toLowerCase();
  $('stat-total').textContent=videos.length;$('stat-ready').textContent=videos.filter(v=>v.status!=='ended').length;
  $('stat-ended').textContent=videos.filter(v=>v.status==='ended').length;
  const rows=videos.filter(v=>(filter==='all'||(filter==='ready'?v.status!=='ended':v.status===filter))&&(v.title+' '+v.url).toLowerCase().includes(q));
  $('count').textContent=rows.length+' รายการ';
  $('rows').innerHTML=rows.map(v=>`<tr><td><div class="media"><span class="media-icon">${icon('play')}</span><div><a class="media-title" href="${v.url}" target="_blank" rel="noopener" title="${esc(v.title)}">${esc(v.title)}</a><a class="source" href="${v.url}" target="_blank" rel="noopener">${v.url}</a></div></div></td><td><span class="badge ${v.status==='error'?'error-badge':v.status}">${labels[v.status]||labels.ready}</span>${v.durationSeconds?`<div class="mini">${Math.floor(v.watchedSeconds||0)} / ${Math.floor(v.durationSeconds)} วินาที</div>`:''}</td><td class="mini">${esc(new Date(v.createdAt).toLocaleString('th-TH'))}</td><td><div class="actions"><button class="icon-btn" data-action="play" data-id="${v.id}" aria-label="เล่น ${esc(v.title)}" title="เล่นวิดีโอ">${icon('play')}</button><button class="icon-btn" data-action="edit" data-id="${v.id}" aria-label="แก้ชื่อ ${esc(v.title)}" title="แก้ชื่อ">${icon('settings')}</button><button class="icon-btn" data-action="remove" data-id="${v.id}" aria-label="ลบรายการ ${esc(v.title)}" title="ลบออกจากคลัง">×</button></div></td></tr>`).join('');
  $('empty').classList.toggle('hidden',rows.length>0);
  $('empty-text').textContent=videos.length?'ไม่พบรายการที่ตรงกับคำค้นหาหรือตัวกรอง':'วางลิงก์ YouTube ด้านบน แล้วกดเพิ่มเข้าคลัง ข้อมูลจะเก็บในเบราว์เซอร์นี้';
  $('storage-status').textContent=storageReady?'บันทึกในเบราว์เซอร์ · '+videos.length+' รายการ':'ไม่สามารถเปิดพื้นที่จัดเก็บได้';
}
async function save(video){
  // Serialize writes so an older player progress write cannot overwrite its end status.
  const snapshot={...video};
  saving=saving.catch(()=>{}).then(()=>storage.put(snapshot));
  await saving;
}
async function setStatus(id,status,extra={}){
  const v=videos.find(v=>v.id===id);if(!v)return;
  Object.assign(v,extra,{status,updatedAt:now()});
  if(status==='playing')v.lastPlayedAt=now();
  render();try{await save(v);}catch{toast('บันทึกข้อมูลไม่ได้ กรุณาส่งออกรายการไว้');}
}
function loadYT(){
  if(globalThis.YT?.Player)return Promise.resolve();
  if(ytPromise)return ytPromise;
  ytPromise=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('โหลดเครื่องเล่นไม่ได้ กรุณาตรวจสอบการเชื่อมต่อ YouTube')),15000);
    globalThis.onYouTubeIframeAPIReady=()=>{clearTimeout(timer);resolve();};
    const script=document.createElement('script');script.src='https://www.youtube.com/iframe_api';script.id='yt-api';
    script.onerror=()=>{clearTimeout(timer);reject(Error('โหลด YouTube ไม่ได้ กรุณาตรวจสอบเครือข่าย'));};
    document.head.appendChild(script);
  }).catch(e=>{ytPromise=null;document.getElementById('yt-api')?.remove();throw e;});
  return ytPromise;
}
function progress(){
  if(!player||!currentId||typeof player.getCurrentTime!=='function')return {};
  return {watchedSeconds:Math.max(0,player.getCurrentTime()||0),durationSeconds:Math.max(0,player.getDuration()||0)};
}
async function closePlayer(){
  playGeneration++;
  const old=currentId,extra=progress();currentId=null;
  if(player){player.destroy();player=null;}
  $('player-card').classList.add('hidden');
  if(old&&videos.some(v=>v.id===old&&v.status==='playing'))await setStatus(old,'paused',extra);
}
async function play(id){
  await closePlayer();const v=videos.find(v=>v.id===id);if(!v)return;
  const generation=++playGeneration;currentId=id;
  $('player-card').classList.remove('hidden');$('player-title').textContent=v.title;$('play-status').textContent='กำลังโหลดเครื่องเล่น…';
  $('player-card').scrollIntoView({behavior:'smooth',block:'center'});
  try{
    await loadYT();if(generation!==playGeneration)return;
    const frame=document.querySelector('.video-frame');frame.innerHTML='<div id="player"></div>';
    player=new YT.Player('player',{host:'https://www.youtube-nocookie.com',videoId:v.videoId,
      playerVars:{autoplay:1,playsinline:1,rel:0,origin:location.origin},
      events:{onReady:event=>{if(generation===playGeneration){$('play-status').textContent='พร้อมเล่น — กดปุ่มเล่นในวิดีโอหากยังไม่เริ่ม';event.target.playVideo();}},
        onAutoplayBlocked:()=>{if(generation===playGeneration){$('play-status').textContent='กดปุ่มเล่นในวิดีโอเพื่อเริ่ม';setStatus(id,'paused');}},
        onStateChange:async event=>{
          if(generation!==playGeneration)return;
          const state={1:'playing',2:'paused',0:'ended'}[event.data];if(!state)return;
          $('play-status').textContent=labels[state];await setStatus(id,state,progress());
          if(state==='ended'&&$('auto-next').checked&&generation===playGeneration){
            const index=videos.findIndex(v=>v.id===id);const next=videos.slice(index+1).find(v=>v.status!=='ended');
            if(next)await play(next.id);else toast('เล่นรายการครบแล้ว');
          }
        },
        onError:event=>{if(generation!==playGeneration)return;$('play-status').textContent='เล่นไม่ได้ (รหัส '+event.data+') — เปิดลิงก์บน YouTube ได้โดยตรง';setStatus(id,'error');}
      }});
  }catch(e){if(generation===playGeneration){$('play-status').textContent=e.message;await setStatus(id,'error');toast(e.message);}}
}
$('add-form').onsubmit=async e=>{
  e.preventDefault();if(loading||!storageReady)return;loading=true;$('add').disabled=true;
  try{
    const id=videoId($('youtube-url').value);if(videos.some(v=>v.videoId===id))throw Error('มีวิดีโอนี้ในคลังแล้ว ใช้ช่องค้นหาเพื่อเปิดรายการได้');
    const v={id:uid(),videoId:id,url:canonical(id),title:$('video-title').value.trim()||'YouTube · '+id,status:'ready',createdAt:now(),updatedAt:now(),watchedSeconds:0,durationSeconds:0};
    await save(v);videos.push(v);$('add-form').reset();render();toast('เพิ่มเข้าคลังและบันทึกแล้ว');
  }catch(e){toast(e.message);}finally{loading=false;$('add').disabled=!storageReady;}
};
$('rows').onclick=async e=>{
  const button=e.target.closest('[data-action]');if(!button)return;const v=videos.find(v=>v.id===button.dataset.id);if(!v)return;
  if(button.dataset.action==='play')return play(v.id);
  if(button.dataset.action==='edit'){editId=v.id;$('edit-title').value=v.title;$('edit-dialog').showModal();return;}
  if(!confirm('ลบรายการ “'+v.title+'” ออกจากคลัง? ไฟล์ JSON ที่เคยส่งออกยังนำกลับเข้ามาได้'))return;
  try{if(currentId===v.id)await closePlayer();await saving.catch(()=>{});await storage.remove(v.id);videos=videos.filter(row=>row.id!==v.id);render();toast('ลบรายการแล้ว');}catch{toast('ลบรายการไม่สำเร็จ');}
};
$('edit-form').onsubmit=async e=>{e.preventDefault();const v=videos.find(v=>v.id===editId);if(!v)return;
  const title=$('edit-title').value.trim();if(!title)return;
  try{const changed={...v,title,updatedAt:now()};await save(changed);Object.assign(v,changed);if(currentId===v.id)$('player-title').textContent=title;$('edit-dialog').close();render();toast('บันทึกชื่อแล้ว');}catch{toast('บันทึกชื่อไม่ได้');}};
$('edit-close').onclick=()=>$('edit-dialog').close();$('close-player').onclick=closePlayer;
$('search').oninput=render;
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-selected',b===button?'true':'false');});render();});
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>{const settings=button.dataset.page==='settings';$('library-page').classList.toggle('hidden',settings);$('settings-page').classList.toggle('hidden',!settings);document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b===button));});
$('export').onclick=()=>{
  const blob=new Blob([JSON.stringify({version:2,exportedAt:now(),videos},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='video-vault-v2-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('ส่งออกเฉพาะรายการและประวัติ ไม่มีไฟล์วิดีโอ');
};
$('import').onclick=()=>$('import-file').click();
$('import-file').onchange=async e=>{
  const file=e.target.files[0];if(!file)return;
  try{
    if(file.size>2*1024*1024)throw Error('รองรับ JSON ขนาดไม่เกิน 2 MB');
    const data=JSON.parse(await file.text());if(data.version!==2||!Array.isArray(data.videos)||data.videos.length>1000)throw Error('ไฟล์รายการ V2 ไม่ถูกต้อง หรือมีมากกว่า 1,000 รายการ');
    const known=new Set(videos.map(v=>v.videoId));const added=[];
    for(const row of data.videos){
      const id=videoId(row.url);if(known.has(id))continue;known.add(id);
      added.push({id:uid(),videoId:id,url:canonical(id),title:String(row.title||'YouTube · '+id).slice(0,200),
        status:['ended','error','paused'].includes(row.status)?row.status:'ready',
        createdAt:Number.isFinite(Date.parse(row.createdAt))?new Date(row.createdAt).toISOString():now(),updatedAt:now(),
        watchedSeconds:Number.isFinite(row.watchedSeconds)?Math.max(0,row.watchedSeconds):0,
        durationSeconds:Number.isFinite(row.durationSeconds)?Math.max(0,row.durationSeconds):0});
    }
    await saving.catch(()=>{});await storage.putAll(added);videos.push(...added);render();toast('นำเข้า '+added.length+' รายการ โดยข้ามวิดีโอที่มีอยู่แล้ว');
  }catch(e){toast(e.message);}finally{e.target.value='';}
};
setInterval(()=>{const v=videos.find(v=>v.id===currentId);if(v?.status==='playing'){Object.assign(v,progress(),{updatedAt:now()});save(v).catch(()=>{});}},3000);
try{
  videos=await storage.list();
  for(const v of videos){if(v.status==='playing'){v.status='paused';await storage.put(v);}}
  storageReady=true;render();
}catch(e){$('add').disabled=true;$('import').disabled=true;render();toast('เปิด IndexedDB ไม่ได้ รายการใหม่จะไม่ถูกบันทึก: '+e.message);}
