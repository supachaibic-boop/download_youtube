let dbPromise;
function openDB(){
  if(!dbPromise) dbPromise=new Promise((resolve,reject)=>{
    if(!globalThis.indexedDB){reject(Error('เบราว์เซอร์นี้ไม่รองรับ IndexedDB'));return;}
    const request=indexedDB.open('video-vault-v2',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('videos',{keyPath:'id'});
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
    request.onblocked=()=>reject(Error('กรุณาปิดแท็บเก่าของเว็บไซต์แล้วลองใหม่'));
  });
  return dbPromise;
}
async function transaction(mode,action){
  const db=await openDB();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('videos',mode);let result;
    const req=action(tx.objectStore('videos'));
    if(req)req.onsuccess=()=>result=req.result;
    tx.oncomplete=()=>resolve(result);
    tx.onerror=()=>reject(tx.error||Error('บันทึกรายการไม่ได้'));
    tx.onabort=()=>reject(tx.error||Error('พื้นที่จัดเก็บไม่พร้อมใช้งาน'));
  });
}
export const list=()=>transaction('readonly',store=>store.getAll());
export const put=video=>transaction('readwrite',store=>store.put(video));
export const remove=id=>transaction('readwrite',store=>store.delete(id));
export const putAll=videos=>transaction('readwrite',store=>{for(const video of videos)store.put(video);});
