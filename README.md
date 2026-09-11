# ⚡ NPD-TEAM Operation Center

แอป Streamlit สำหรับบริหารจัดการโปรเจกต์ทีม NPD พร้อม:
- ระบบล็อกอิน สร้างผู้ใช้ใหม่ได้ กำหนดสิทธิ์ (admin / member) ได้
- ฐานข้อมูลเก็บบน **Google Sheets** ทั้งตารางผู้ใช้ (`Users`) และตารางโปรเจกต์ (`Data`)
- หน้า Dashboard สรุปภาพรวม, ค้นหาขั้นสูง, ตารางแก้ไขข้อมูลได้โดยตรง

---

## 1) โครงสร้างไฟล์

```
npd-dashboard/
├── app.py
├── requirements.txt
├── README.md
└── .streamlit/
    └── secrets.toml.example   ← คัดลอกเป็น secrets.toml แล้วใส่ค่าจริง
```

## 2) การตั้งค่า Google Cloud (ทำครั้งเดียว)

1. ไปที่ [Google Cloud Console](https://console.cloud.google.com/) → สร้างโปรเจกต์ใหม่ (หรือใช้โปรเจกต์เดิม)
2. เปิดใช้งาน API 2 ตัว: **Google Sheets API** และ **Google Drive API**
   (เมนู "APIs & Services" → "Enable APIs and Services" → ค้นหาแล้วกด Enable)
3. สร้าง Service Account: "APIs & Services" → "Credentials" → "Create Credentials" → "Service account"
   - ตั้งชื่ออะไรก็ได้ เช่น `npd-dashboard-bot`
4. เข้าไปที่ Service Account ที่สร้าง → แท็บ "Keys" → "Add Key" → "Create new key" → เลือก **JSON** → ดาวน์โหลดไฟล์
5. เปิดไฟล์ JSON ที่ได้ แล้วคัดลอกค่าแต่ละ field ไปใส่ในส่วน `[gcp_service_account]` ของ `secrets.toml`

## 3) สร้าง Google Sheet

1. สร้าง Google Sheet ใหม่ (จะมีข้อมูลในชีตหรือไม่ก็ได้ แอปจะสร้างแท็บ `Users` และ `Data` ให้อัตโนมัติ)
2. คัดลอก Sheet ID จาก URL:
   `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`
3. **แชร์ (Share)** ชีตนี้ให้กับอีเมลของ Service Account (ค่า `client_email` ในไฟล์ JSON)
   โดยให้สิทธิ์เป็น **Editor** — ขั้นตอนนี้สำคัญมาก ถ้าลืมแอปจะเชื่อมต่อไม่ได้

## 4) ตั้งค่า secrets.toml

คัดลอก `.streamlit/secrets.toml.example` เป็น `.streamlit/secrets.toml` แล้วกรอกค่า:
- `[cookie]` → ตั้งชื่อคุกกี้และ key แบบสุ่มของคุณเอง
- `[gsheet]` → ใส่ Sheet ID จากขั้นตอนก่อนหน้า
- `[gcp_service_account]` → ใส่ค่าจากไฟล์ JSON ของ Service Account

> ⚠️ **อย่า commit ไฟล์ `secrets.toml` ที่มีค่าจริงขึ้น GitHub** ให้เพิ่มบรรทัด
> `.streamlit/secrets.toml` ลงใน `.gitignore` เสมอ

## 5) รันบนเครื่องตัวเอง (VS Code)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 6) Deploy ขึ้น Streamlit Community Cloud

1. Push โค้ด (ไม่รวม `secrets.toml` จริง) ขึ้น GitHub ตามปกติ
2. ไปที่ [share.streamlit.io](https://share.streamlit.io) → New app → เลือก repo/branch/`app.py`
3. ก่อนหรือหลัง deploy ก็ได้: เข้า **App settings → Secrets** แล้ววางเนื้อหาทั้งหมดจาก `secrets.toml` (ที่กรอกค่าจริงแล้ว) ลงไป → Save
4. แอปจะรีสตาร์ทและเชื่อมต่อ Google Sheet ได้ทันที

## 7) การใช้งานครั้งแรก

- เปิดแอปครั้งแรก ระบบจะยังไม่มีผู้ใช้งาน → จะมีฟอร์ม **"สร้างบัญชีแอดมินคนแรก"** ขึ้นมาอัตโนมัติ
- กรอก Username/รหัสผ่านเพื่อสร้างบัญชีแอดมิน → ระบบจะบันทึกลงแท็บ `Users` ในชีต (รหัสผ่านถูกเข้ารหัสแบบ bcrypt เสมอ ไม่เก็บเป็น plain text)
- ล็อกอินด้วยบัญชีแอดมินที่สร้าง → ไปที่แท็บ **"👥 จัดการผู้ใช้"** เพื่อเพิ่มสมาชิกทีมคนอื่น ๆ หรือเปลี่ยนสิทธิ์ admin/member

## 8) โครงสร้างข้อมูลใน Google Sheet

**แท็บ `Users`**
| Username | FirstName | LastName | Email | Password (hash) | Roles |

**แท็บ `Data`**
| ID | ProjectName | Category | Owner | StartDate | Status | Priority | Budget | Progress | Description | CreatedAt | UpdatedAt |

ทั้งสองแท็บจะถูกสร้างอัตโนมัติหากยังไม่มี ไม่ต้องสร้างเองล่วงหน้า

## 9) ฟีเจอร์หลักในแอป

- ✍️ **บันทึกงานใหม่** — ฟอร์มเพิ่มโปรเจกต์ พร้อมรหัสอัตโนมัติ (P001, P002, ...)
- 📋 **ตารางงานทั้งหมด** — แก้ไข/ลบ/เพิ่มแถวได้โดยตรงในตาราง แล้วกดบันทึกเพื่ออัปเดตชีต
- 📊 **Dashboard** — กราฟสัดส่วนสถานะ, ความสำคัญ, งบประมาณตามหมวดหมู่, ความคืบหน้ารายโปรเจกต์
- 🔎 **ค้นหาขั้นสูง** — ค้นหาด้วยคำค้น + กรองหมวดหมู่/ช่วงวันที่/ความคืบหน้า + ดาวน์โหลด CSV
- 👥 **จัดการผู้ใช้** (เฉพาะ admin) — เพิ่มผู้ใช้ใหม่, ดูรายชื่อ, เปลี่ยนสิทธิ์
- 🔑 **เปลี่ยนรหัสผ่านตัวเอง** — ทำได้จากแถบด้านข้าง (sidebar) ทุกบัญชี

## 10) ข้อจำกัดที่ควรรู้

- ข้อมูลถูกอ่าน/แคชไว้สั้น ๆ (15–20 วินาที) เพื่อลดการเรียก Google Sheets API บ่อยเกินไป
  หากมีคนอื่นแก้ไขพร้อมกัน อาจต้องรอสักครู่หรือรีเฟรชหน้าเพื่อเห็นข้อมูลล่าสุด
- Google Sheets API มีโควตาการเรียกใช้งานฟรี (โดยทั่วไปเพียงพอสำหรับทีมขนาดเล็ก-กลาง)
- ตาราง "ตารางงานทั้งหมด" จะบันทึกข้อมูลทั้งหมดทับชีตทุกครั้งที่กด "บันทึกการเปลี่ยนแปลง"
  จึงควรกดบันทึกหลังแก้ไขเสร็จ ไม่ต้องกดบ่อยระหว่างพิมพ์
