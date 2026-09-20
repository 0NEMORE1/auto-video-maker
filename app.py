import streamlit as st
import os
import asyncio
import requests
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips
import tempfile
import uuid

# ==========================================
# 1. ตั้งค่าพื้นฐาน Streamlit
# ==========================================
st.set_page_config(page_title="AI Auto Video Maker", page_icon="🎬", layout="wide")

# สร้างโฟลเดอร์ชั่วคราวสำหรับเก็บไฟล์ขณะรันบนเซิร์ฟเวอร์
WORK_DIR = tempfile.mkdtemp()
STANDARD_SIZE = (1280, 720) # ใช้ HD 720p เพื่อให้ประมวลผลบนเว็บได้เร็วขึ้น

st.title("🎬 AI Auto Video Maker")
st.markdown("โปรแกรมสร้างวิดีโออัตโนมัติจากสคริปต์ (ค้นหาคลิป Pexels + เสียงพากย์ AI ภาษาไทย)")

# ==========================================
# 2. ส่วนรับข้อมูลจากผู้ใช้ (UI)
# ==========================================
with st.sidebar:
    st.header("⚙️ การตั้งค่า")
    pexels_key = st.text_input("Pexels API Key", type="password", help="รับฟรีที่ https://www.pexels.com/api/")
    voice_option = st.selectbox("เลือกเสียงพากย์", ["th-TH-NiwatNeural (ชาย)", "th-TH-PremwadeeNeural (หญิง)"])
    voice_code = voice_option.split(" ")[0]

st.subheader("📝 ใส่สคริปต์ของคุณ")
st.markdown("รูปแบบ: ข้อความพากย์ | คีย์เวิร์ดค้นหาวิดีโอ (ภาษาอังกฤษ) -- พิมพ์บรรทัดละฉาก")

default_script = """สวัสดีครับทุกคน ขอต้อนรับสู่ทริปอุซเบกิสถาน | uzbekistan city
วันนี้เราจะไปขี่อูฐลุยทะเลทรายกันครับ | camel desert
ปิดท้ายด้วยการชมสถาปัตยกรรมมัสยิดโบราณ | mosque architecture"""

script_text = st.text_area("สคริปต์วิดีโอ", value=default_script, height=200)

# ==========================================
# 3. ฟังก์ชันหลักสำหรับประมวลผล
# ==========================================
def download_stock_video(keyword, output_filename, api_key):
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=1&orientation=landscape"
    headers = {"Authorization": api_key}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data['videos']:
                video_files = data['videos'][0]['video_files']
                # หาคลิปที่ความละเอียดใกล้ 720p หรือ 1080p
                hd_file = next((file for file in video_files if file['quality'] == 'hd'), video_files[0])
                video_url = hd_file['link']
                
                vid_response = requests.get(video_url)
                with open(output_filename, 'wb') as f:
                    f.write(vid_response.content)
                return True
            else:
                st.warning(f"ไม่พบวิดีโอสำหรับคำว่า '{keyword}'")
                return False
        else:
            st.error(f"เกิดข้อผิดพลาดจาก Pexels API (Status: {response.status_code}). โปรดเช็ก API Key")
            return False
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดาวน์โหลด: {e}")
        return False

async def generate_audio(text, output_filename, voice):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

async def process_video(scenes_data, api_key, voice, progress_bar, status_text):
    final_clips = []
    
    for i, scene in enumerate(scenes_data):
        status_text.text(f"กำลังประมวลผลฉากที่ {i+1}/{len(scenes_data)}...")
        
        # ตั้งชื่อไฟล์ชั่วคราว
        unique_id = uuid.uuid4().hex[:6]
        audio_path = os.path.join(WORK_DIR, f"scene_{i}_{unique_id}.mp3")
        video_path = os.path.join(WORK_DIR, f"scene_{i}_{unique_id}.mp4")
        
        # 1. สร้างเสียง
        await generate_audio(scene["text"], audio_path, voice)
        
        # 2. โหลดคลิป
        has_video = download_stock_video(scene["keyword"], video_path, api_key)
        
        if has_video:
            # 3. ประกอบคลิป
            audio_clip = AudioFileClip(audio_path)
            video_clip = VideoFileClip(video_path)
            
            video_clip = video_clip.resize(STANDARD_SIZE)
            
            if video_clip.duration < audio_clip.duration:
                video_clip = video_clip.set_duration(audio_clip.duration)
            else:
                video_clip = video_clip.subclip(0, audio_clip.duration)
                
            final_scene = video_clip.set_audio(audio_clip)
            final_clips.append(final_scene)
            
        progress_bar.progress((i + 1) / len(scenes_data))
        
    status_text.text("กำลังรวมคลิปเป็นไฟล์เดียว (เรนเดอร์)... อาจใช้เวลาสักครู่")
    if final_clips:
        output_file = os.path.join(WORK_DIR, f"AutoVideo_{uuid.uuid4().hex[:6]}.mp4")
        final_movie = concatenate_videoclips(final_clips, method="compose")
        
        # รันแบบเบาๆ เพื่อเซิร์ฟเวอร์ฟรี
        final_movie.write_videofile(
            output_file, 
            fps=24, 
            codec="libx264", 
            audio_codec="aac",
            preset="ultrafast",
            logger=None
        )
        
        final_movie.close()
        for clip in final_clips:
            clip.close()
            
        return output_file
    return None

# ==========================================
# 4. ปุ่มเริ่มทำงาน
# ==========================================
if st.button("🚀 สร้างวิดีโอทันที", type="primary"):
    if not pexels_key:
        st.error("กรุณาใส่ Pexels API Key ในเมนูด้านซ้ายก่อนครับ!")
    elif not script_text.strip():
        st.error("กรุณาใส่สคริปต์ก่อนครับ!")
    else:
        # แปลงข้อความเป็นข้อมูลฉาก
        scenes_data = []
        for line in script_text.strip().split('\n'):
            if "|" in line:
                text, keyword = line.split("|", 1)
                scenes_data.append({"text": text.strip(), "keyword": keyword.strip()})
        
        if not scenes_data:
            st.error("รูปแบบสคริปต์ไม่ถูกต้อง ต้องมีเครื่องหมาย | คั่นระหว่างข้อความและคีย์เวิร์ด")
        else:
            progress_bar = st.progress(0)
