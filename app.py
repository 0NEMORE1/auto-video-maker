import streamlit as st
import os
import asyncio
import requests
import edge_tts
import tempfile
import uuid
import zipfile

# ==========================================
# 1. ตั้งค่าพื้นฐาน Streamlit
# ==========================================
st.set_page_config(page_title="AI Video Asset Maker", page_icon="🎬", layout="wide")

WORK_DIR = tempfile.mkdtemp()

st.title("🎬 AI Video Asset Maker")
st.markdown("เครื่องมือช่วยสร้างทรัพย์สินสำหรับตัดต่อวิดีโอ (เสียงพากย์ AI และ คลิปฟุตเทจ)")

# ==========================================
# 2. ฟังก์ชันการทำงานหลัก
# ==========================================
async def generate_audio(text, output_filename, voice):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

def search_and_download_video(keyword, output_filename, api_key):
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=1&orientation=landscape"
    headers = {"Authorization": api_key}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get('videos') and len(data['videos']) > 0:
                video_files = data['videos'][0]['video_files']
                # เลือกไฟล์ HD หรือคุณภาพสูงสุดที่มี
                best_file = next((f for f in video_files if f['quality'] == 'hd' and f['height'] == 720), None)
                if not best_file:
                    best_file = video_files[0]
                
                vid_response = requests.get(best_file['link'])
                with open(output_filename, 'wb') as f:
                    f.write(vid_response.content)
                return True
    except Exception as e:
        print(f"Error downloading {keyword}: {e}")
    return False

# ==========================================
# 3. ส่วนแสดงผล UI (แยก Tabs)
# ==========================================
tab1, tab2 = st.tabs(["🎙️ สร้างเสียงพากย์ AI", "🎞️ ค้นหาและโหลดคลิปฟุตเทจ"])

# ------------------------------------------
# TAB 1: สร้างเสียงพากย์ AI
# ------------------------------------------
with tab1:
    st.header("🎙️ สร้างเสียงพากย์ AI (ทีละหลายไฟล์)")
    st.markdown("พิมพ์ข้อความที่ต้องการให้ AI พากย์ 1 บรรทัด = 1 ไฟล์เสียง")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        voice_option = st.selectbox("เลือกเสียงพากย์", ["th-TH-NiwatNeural (ชาย)", "th-TH-PremwadeeNeural (หญิง)"], key="voice_sel")
        voice_code = voice_option.split(" ")[0]
    
    with col2:
        default_audio_script = "สวัสดีครับทุกคน ขอต้อนรับสู่ทริปอุซเบกิสถาน\nวันนี้เราจะไปขี่อูฐลุยทะเลทรายกันครับ"
        audio_text = st.text_area("สคริปต์เสียง (บรรทัดละ 1 ประโยค)", value=default_audio_script, height=150)
        
    if st.button("🎙️ เจนเสียงพากย์", type="primary", use_container_width=True):
        lines = [line.strip() for line in audio_text.split('\n') if line.strip()]
        if not lines:
            st.error("กรุณาใส่ข้อความสคริปต์")
        else:
            progress_text = st.empty()
            progress_bar = st.progress(0)
            audio_files = []
            
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                for i, line in enumerate(lines):
                    progress_text.text(f"กำลังเจนเสียงที่ {i+1}/{len(lines)}: {line[:30]}...")
                    progress_bar.progress((i) / len(lines))
                    
                    filename = os.path.join(WORK_DIR, f"voice_{i+1:02d}_{uuid.uuid4().hex[:4]}.mp3")
                    loop.run_until_complete(generate_audio(line, filename, voice_code))
                    audio_files.append((f"voice_{i+1:02d}.mp3", filename))
                
                progress_bar.progress(1.0)
                progress_text.text("✅ สร้างเสียงเสร็จสมบูรณ์!")
                
                # นำไฟล์ทั้งหมดใส่ ZIP ให้โหลดทีเดียว
                zip_path = os.path.join(WORK_DIR, f"Audio_Assets_{uuid.uuid4().hex[:4]}.zip")
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for arcname, filepath in audio_files:
                        zipf.write(filepath, arcname)
                        
                with open(zip_path, "rb") as fp:
                    st.download_button(
                        label="📦 ดาวน์โหลดเสียงทั้งหมด (.zip)",
                        data=fp,
                        file_name="Voiceover_Assets.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")

# ------------------------------------------
# TAB 2: โหลดคลิปฟุตเทจ
# ------------------------------------------
with tab2:
    st.header("🎞️ ค้นหาและโหลดคลิปฟุตเทจ (Pexels)")
    st.markdown("พิมพ์คำค้นหาภาษาอังกฤษ 1 บรรทัด = 1 คลิปวิดีโอ")
    
    col3, col4 = st.columns([1, 3])
    with col3:
        api_key_input = st.text_input("Pexels API Key", type="password", key="pexels_key")
        st.markdown("[ขอ API Key ฟรีที่นี่](https://www.pexels.com/api/)")
    
    with col4:
        default_video_keywords = "uzbekistan city\ncamel desert\nmosque architecture"
        video_keywords = st.text_area("คีย์เวิร์ดวิดีโอ (ภาษาอังกฤษ บรรทัดละ 1 คำ)", value=default_video_keywords, height=150)
        
    if st.button("🎞️ ค้นหาและโหลดวิดีโอ", type="primary", use_container_width=True):
        if not api_key_input:
            st.error("กรุณาใส่ Pexels API Key")
        else:
            keywords = [k.strip() for k in video_keywords.split('\n') if k.strip()]
            if not keywords:
                st.error("กรุณาใส่คีย์เวิร์ดอย่างน้อย 1 คำ")
            else:
                v_progress_text = st.empty()
                v_progress_bar = st.progress(0)
                video_files = []
                
                for i, kw in enumerate(keywords):
                    v_progress_text.text(f"กำลังค้นหาคลิปที่ {i+1}/{len(keywords)}: '{kw}'...")
                    v_progress_bar.progress((i) / len(keywords))
                    
                    filename = os.path.join(WORK_DIR, f"video_{i+1:02d}_{kw.replace(' ', '_')}.mp4")
                    success = search_and_download_video(kw, filename, api_key_input)
                    
                    if success:
                        video_files.append((f"video_{i+1:02d}_{kw.replace(' ', '_')}.mp4", filename))
                    else:
                        st.warning(f"⚠️ ไม่พบคลิปสำหรับคำว่า: '{kw}'")
                
                v_progress_bar.progress(1.0)
                
                if video_files:
                    v_progress_text.text(f"✅ โหลดวิดีโอสำเร็จ {len(video_files)} คลิป!")
                    
                    # นำไฟล์ทั้งหมดใส่ ZIP
                    v_zip_path = os.path.join(WORK_DIR, f"Video_Assets_{uuid.uuid4().hex[:4]}.zip")
                    with zipfile.ZipFile(v_zip_path, 'w') as zipf:
                        for arcname, filepath in video_files:
                            zipf.write(filepath, arcname)
                            
                    with open(v_zip_path, "rb") as fp:
                        st.download_button(
                            label="📦 ดาวน์โหลดวิดีโอทั้งหมด (.zip)",
                            data=fp,
                            file_name="Footage_Assets.zip",
                            mime="application/zip",
                            use_container_width=True,
                            type="secondary"
                        )
                else:
                    v_progress_text.text("❌ ไม่สามารถโหลดวิดีโอได้เลย กรุณาตรวจสอบคีย์เวิร์ดหรือ API Key")
