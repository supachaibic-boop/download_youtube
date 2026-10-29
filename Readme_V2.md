# Video Vault V2 — GitHub Pages edition

V2 เป็นเว็บแบบ static สำหรับวางลิงก์ จัดรายการ และเล่น YouTube ภายในหน้าเว็บ ใช้ GitHub Pages แทน Docker และเก็บข้อมูลส่วนตัวด้วย IndexedDB ของเบราว์เซอร์

**V2 ไม่ดาวน์โหลด ไม่อัดสตรีม และไม่สร้างไฟล์ MP4/MP3** หากต้องการบันทึกวิดีโอจริง ให้ใช้รุ่น Docker ใน branch `v1`

## สถานะการเผยแพร่

**Deploy สำเร็จและเปิดเว็บไซต์จริงตรวจสอบแล้ว วันที่ 29 ตุลาคม 2569**

เปิดใช้งาน: **https://supachaibic-boop.github.io/download_youtube/**

- Repository เป็น **Public** ตามที่เจ้าของอนุญาต ซอร์สทุก branch รวม `v1` เปิดให้ดูได้
- GitHub Pages ใช้ **Deploy from a branch → main → /docs** และบังคับ HTTPS
- Deployment ที่ยืนยันสำเร็จ: https://github.com/supachaibic-boop/download_youtube/actions/runs/40862610686
- ตรวจหน้าเว็บจริงแล้ว: โหลด HTML/CSS/JavaScript ได้ เพิ่มรายการสำเร็จ และข้อมูล IndexedDB ยังอยู่หลังรีโหลด
- รายการส่วนตัวอยู่เฉพาะในเบราว์เซอร์ ไม่ได้ถูกส่งขึ้น repository และไม่ปรากฏแก่ผู้เข้าชมคนอื่น

## สำรองรุ่นเดิมก่อนเปลี่ยน

สำรองเป็น branch [`v1`](https://github.com/supachaibic-boop/download_youtube/tree/v1) จาก commit:

`b82a8d8b5c1cb30f062ae6371aaca9f248cadd71`

เป็นรุ่น Docker ล่าสุดก่อนเริ่ม V2 รวม Python, SQLite, FFmpeg, โหมดบันทึกสตรีม 1×, compose.yaml, Dockerfile และสคริปต์เริ่มใช้งานทั้งหมด การสำรองใน Git ครอบคลุมซอร์สเท่านั้น ไม่รวมไฟล์ `.env`, ฐานข้อมูล หรือวิดีโอในเครื่องผู้ใช้

## สิ่งที่คงไว้และสิ่งที่เปลี่ยน

| ความสามารถ | V1 Docker | V2 GitHub Pages |
|---|---|---|
| วางลิงก์ YouTube / Shorts | มี | มี |
| แสดงชื่อและลิงก์ต้นทาง | มี | มี ตั้งชื่อเองหรือใช้ video ID |
| เล่น YouTube ในหน้าเว็บ | ไม่มีเครื่องเล่นแบบฝัง | มี YouTube player |
| สถานะ | ดาวน์โหลด/บันทึก/สำเร็จ/ล้มเหลว | พร้อมเล่น/กำลังเล่น/หยุด/เล่นจบ/เล่นไม่ได้ |
| เล่นรายการต่อไป | ไม่มี | เลือกเปิดได้ |
| บันทึกสตรีมเบื้องหลังจนจบ | มี FFmpeg | ไม่มี |
| ดาวน์โหลดหรือแปลง MP4/MP3 | มี | ไม่มี |
| ชื่อไฟล์ ขนาด ตำแหน่งไฟล์ | มี | ไม่มี เพราะไม่สร้างไฟล์สื่อ |
| SQLite ฝั่งเซิร์ฟเวอร์ | มี | ไม่มี |
| เก็บรายชื่อและประวัติ | SQLite บน Docker host | IndexedDB ในเบราว์เซอร์ |
| ส่งออก/นำเข้ารายการ | ไม่มีในหน้าเว็บ V1 | JSON |
| ซิงก์หลายอุปกรณ์ | เซิร์ฟเวอร์เดียวกัน | ไม่มี ใช้ JSON ย้ายข้อมูล |
| Google API key | ไม่ใช้ | ไม่ใช้ |
| API_TOKEN | ใช้เชื่อมต่อ backend | ไม่ใช้ |
| Docker / Python / FFmpeg | ต้องใช้ | ไม่ต้องใช้ |

GitHub Pages ให้บริการไฟล์ HTML/CSS/JavaScript แต่ไม่ได้รัน worker Python, FFmpeg หรือ SQLite server หน้าเว็บ YouTube iframe ไม่ส่ง raw stream ให้ JavaScript ของเว็บไซต์บันทึกเป็นไฟล์ ดังนั้น V2 ไม่มีปุ่มดาวน์โหลดที่อ้างว่าสามารถดึงไฟล์จากเครื่องเล่นได้

## เปิด GitHub Pages

1. ไปที่ [Settings → Pages](https://github.com/supachaibic-boop/download_youtube/settings/pages) โดยลงชื่อเข้าใช้ GitHub เจ้าของ repository
2. ส่วน **Build and deployment** เลือก **Source → Deploy from a branch**
3. เลือก branch **main** และ folder **/docs** แล้วกด **Save**
4. รอ GitHub แสดงว่า deployment สำเร็จ แล้วใช้ URL จากปุ่ม **Visit site** เป็น URL จริงของเว็บไซต์
5. หาก GitHub แสดงให้ upgrade plan สำหรับ private repository จะต้องใช้แผนที่รองรับ หรือเจ้าของตัดสินใจเปลี่ยน repository เป็น Public เอง ซึ่งจะเปิดเผยซอร์สทั้งหมด อย่าเปลี่ยนเพียงเพื่อทดสอบโดยไม่ได้ตรวจสอบก่อน

ไม่มี GitHub Actions workflow พิเศษที่ต้องใส่ secret หรือ API token ใช้ระบบ deploy จาก branch ของ Pages โดยตรง การอัปเดตไฟล์ใน `docs/` จะถูกเผยแพร่เมื่อ Pages เปิดแล้ว

## วิธีใช้

1. เปิด URL เว็บไซต์ Pages ที่ GitHub แสดง
2. วางลิงก์ YouTube และใส่ชื่อรายการได้ตามต้องการ
3. กด **เพิ่มเข้าคลัง** เพื่อบันทึกรายการลง IndexedDB
4. กดปุ่มเล่นของรายการ เครื่องเล่น YouTube จะปรากฏด้านบน
5. ถ้า autoplay ถูกเบราว์เซอร์ปิดกั้น ให้กด Play ในวิดีโออีกครั้ง
6. เปิด **เล่นรายการถัดไปเมื่อจบ** หากต้องการเล่นรายการถัดจากรายการปัจจุบันตามลำดับในคลัง
7. ใช้ช่องค้นหาและตัวกรอง แก้ชื่อรายการ หรือเปิดลิงก์ต้นทางได้
8. ใช้ **ส่งออกรายการ** เพื่อเก็บ JSON และ **นำเข้ารายการ** เพื่อย้ายไปเบราว์เซอร์หรือเครื่องอื่น การนำเข้าข้ามวิดีโอที่มีอยู่แล้ว

รองรับ URL แบบ HTTPS ของ youtube.com/watch?v=, youtu.be/, youtube.com/shorts/, /live/ และ /embed/ ที่ระบุ video ID ถูกต้อง ไม่ใช่การนำเข้า playlist ของ YouTube

สถานะการเล่นจบมาจาก event ของ YouTube player ไม่ใช่สถานะดาวน์โหลด สถานะไม่ใช่หลักฐานว่าดูครบทุกวินาที เพราะผู้ใช้สามารถเลื่อนเวลาได้

## ข้อมูลอยู่ที่ไหน

- IndexedDB ชื่อ `video-vault-v2`, object store ชื่อ `videos`
- เก็บ ID, URL, ชื่อ, สถานะ, วันเพิ่ม/แก้ไข, เวลาเล่นล่าสุด และความคืบหน้า
- ไม่มีไฟล์วิดีโอใน IndexedDB และไม่มีไฟล์ SQLite
- ไม่ส่งรายชื่อไป GitHub repository หรือ backend ของโครงการนี้
- ข้อมูลแยกตาม browser profile และ origin ของเว็บไซต์ เปลี่ยนโดเมนหรือใช้เครื่องใหม่จะไม่เห็นรายการเดิมจนกว่าจะนำเข้า JSON
- การล้าง Site data หรือปิดโหมด Incognito อาจทำให้ข้อมูลหาย จึงควรส่งออก JSON ไว้
- ไฟล์นำเข้าจำกัด 2 MB และ 1,000 รายการ
- เมื่อรีโหลดระหว่างเล่น สถานะจะกลับเป็นหยุดชั่วคราว การเล่นไม่ได้ทำต่อจาก background service

## ข้อจำกัดเครื่องเล่น

ต้องมีอินเทอร์เน็ตและเข้าถึง YouTube ได้ เนื้อหาที่ปิดการฝังวิดีโอ จำกัดอายุ ภูมิภาค หรือบัญชี อาจเล่นในเว็บไซต์ไม่ได้ ให้เปิดลิงก์บน YouTube โดยตรง เว็บนี้ไม่ข้ามข้อจำกัดเหล่านั้น

ไม่รับประกันการเล่นเมื่อปิดแท็บ ย้ายแอปไป background ล็อกหน้าจอ หรือระบบประหยัดแบตเตอรี่ทำงาน การเปิดเว็บทิ้งไว้ไม่ได้ทำให้เกิดไฟล์บันทึก

## กลับไปใช้ V1

ใช้ checkout แยกเพื่อรักษางานในโฟลเดอร์เดิม:

```powershell
git clone --branch v1 https://github.com/supachaibic-boop/download_youtube.git C:\Users\Acer\download_youtube_v1
cd C:\Users\Acer\download_youtube_v1
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

ต้องเปิด Docker Desktop ก่อน V1 ต้องใช้ `.env` และ `data` ของ V1 เดิมหากต้องการประวัติ/ไฟล์เดิม คำสั่ง clone ไม่ดาวน์โหลดข้อมูลส่วนตัวเหล่านี้กลับมาจาก Git

## โครงสร้าง V2

```text
docs/
  index.html
  style.css
  app.js
  storage.js
  .nojekyll
Readme_V2.md
```

โค้ด Docker ที่ root ยังคงอยู่เพื่อไม่ให้ผู้ใช้เดิมเสีย workflow แต่ Pages เผยแพร่เฉพาะ `docs/` ไม่เผยแพร่ `.env` หรือโฟลเดอร์ `data`

## การตรวจสอบ

- ตรวจ syntax JavaScript ของ app.js และ storage.js
- ตรวจผ่านเบราว์เซอร์จริง: เพิ่มรายการ, IndexedDB คงข้อมูลหลังรีโหลด, แก้ชื่อรายการ และโหลด YouTube iframe
- หลังเจ้าของอนุญาตให้เปลี่ยน repository เป็น Public เปิด Pages สำเร็จและตรวจหน้าเว็บจริง รวมการเพิ่มรายการและเก็บข้อมูลหลังรีโหลด

## เอกสารอ้างอิง

- https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
- https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site
- https://developers.google.com/youtube/iframe_api_reference
