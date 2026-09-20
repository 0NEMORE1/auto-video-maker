import streamlit as st
import os
import asyncio
import requests
import edge_tts
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
import tempfile
import uuid
import gc

# ==========================================
# 1. ตั้งค่าพื้นฐาน Streamlit
# ==========================================
st.set_page_config(page_title="AI Auto Video Maker", page_icon="🎬", layout="wide")

WORK_DIR = tempfile.mkdtemp()
STANDARD_SIZE = (1280, 720) 

st.title("🎬 AI Auto Video Maker (Smart Editor)")
st.markdown("โปรแกรมสร้างวิดีโออัตโนมัติจากสคริปต์ (ค้นหาคลิป Pexels + เสียงพากย์ AI ภาษาไทย)")
st.info("💡 **คำแนะนำสำหรับคลิปยาว:** หากสคริปต์มีความยาวเกิน 5 บรรทัด แนะนำให้แบ่งทำทีละส่วน (Part)")

# ==========================================
# 2. ส่วนรับข้อมูลจากผู้ใช้ (UI)
# ==========================================
with st.sidebar:
    st.header("⚙️ การตั้งค่า")
    pexels_key = st.text_input("Pexels API Key", type="password")
    voice_option = st.selectbox("เลือกเสียงพากย์", ["th-TH-NiwatNeural (ชาย)", "th-TH-PremwadeeNeural (หญิง)"])
    voice_code = voice_option.split(" ")[0]
    
    st.markdown("---")
    st.markdown("### 📝 คำแนะนำการพิมพ์คีย์เวิร์ด")
    st.markdown("- ใช้ภาษาอังกฤษ\n- ใช้ 1-2 คำพอ เช่น `desert`, `train`\n- หากค้นหาคลิปไม่เจอ ระบบจะข้ามฉากนั้นไป")

st.subheader("📝 ใส่สคริปต์ของคุณ")
st.markdown("รูปแบบ: `ข้อความพากย์ภาษาไทย | คีย์เวิร์ดค้นหาวิดีโอ`")

default_script = """สวัสดีครับทุกคน ขอต้อนรับสู่ทริปอุซเบกิสถาน | uzbekistan city
วันนี้เราจะไปขี่อูฐลุยทะเลทรายกันครับ | camel desert"""

script_text = st.text_area("สคริปต์วิดีโอ (วางที่นี่)", value=default_script, height=200)

col1, col2 = st.columns([1, 4])
with col1:
    btn_generate = st.button("🚀 สร้างวิดีโอทันที", type="primary", use_container_width=True)
with col2:
    if st.button("🗑️ ล้างข้อความสคริปต์", use_container_width=True):
        st.session_state.script_text = ""
        st.rerun()

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
            if data.get('videos') and len(data['videos']) > 0:
                video_files = data['videos'][0]['video_files']
                hd_file = next((f for f in video_files if f['quality'] == 'hd' and f['height'] == 720), None)
                if not hd_file:
                     hd_file = video_files[0] 
                
                video_url = hd_file['link']
                vid_response = requests.get(video_url)
                with open(output_filename, 'wb') as f:
                    f.write(vid_response.content)
                return True
            else:
                return False
        else:
            return False
    except Exception as e:
        return False

async def generate_audio(text, output_filename, voice):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

async def process_video(scenes_data, api_key, voice, progress_bar, status_text, detail_text):
    final_clips = []
    total_scenes = len(scenes_data)
    
    for i, scene in enumerate(scenes_data):
        current_step = i + 1
        
        status_text.markdown(f"### 🎬 กำลังประมวลผลฉากที่ {current_step} จาก {total_scenes}")
        progress_bar.progress((i) / (total_scenes + 1))
        
        unique_id = uuid.uuid4().hex[:6]
        audio_path = os.path.join(WORK_DIR, f"scene_{i}_{unique_id}.mp3")
        video_path = os.path.join(WORK_DIR, f"scene_{i}_{unique_id}.mp4")
        
        detail_text.text(f"กำลังสร้างเสียงพากย์: \"{scene['text'][:30]}...\"")
        await generate_audio(scene["text"], audio_path, voice)
        
        detail_text.text(f"กำลังค้นหาและดาวน์โหลดวิดีโอสำหรับคำว่า: '{scene['keyword']}'")
        has_video = download_stock_video(scene["keyword"], video_path, api_key)
        
        if has_video:
            detail_text.text(f"กำลังปรับความยาววิดีโอให้ตรงกับเสียงพากย์...")
            audio_clip = AudioFileClip(audio_path)
            video_clip = VideoFileClip(video_path)
            
            # ย่อขนาดวิดีโอ (moviepy 2.x ใช้ resized)
            video_clip = video_clip.resized(STANDARD_SIZE)
            
            if video_clip.duration < audio_clip.duration:
                # ถ้าวิดีโอสั้นกว่าเสียง ให้ตัดวิดีโอส่วนสุดท้ายทิ้งแล้วทำ loop หรือหยุดค้าง
                video_clip = video_clip.with_duration(audio_clip.duration)
            else:
                video_clip = video_clip.subclipped(0, audio_clip.duration)
                
            final_scene = video_clip.with_audio(audio_clip)
            final_clips.append(final_scene)
        else:
            st.warning(f"⚠️ ฉากที่ {current_step}: ไม่พบวิดีโอสำหรับคำว่า '{scene['keyword']}'")
            
        gc.collect() 
        
    status_text.markdown("### ⚙️ กำลังเรนเดอร์และรวมวิดีโอ (ขั้นตอนนี้อาจใช้เวลาสักครู่...)")
    progress_bar.progress(total_scenes / (total_scenes + 1))
    detail_text.text("กำลังบีบอัดและเขียนไฟล์วิดีโอสุดท้าย โปรดอย่าเพิ่งปิดหน้าต่างนี้...")
    
    if final_clips:
        output_file = os.path.join(WORK_DIR, f"AutoVideo_{uuid.uuid4().hex[:6]}.mp4")
        try:
            final_movie = concatenate_videoclips(final_clips, method="compose")
            final_movie.write_videofile(
                output_file, 
                fps=24, 
                codec="libx264", 
                audio_codec="aac",
                preset="ultrafast", 
                threads=4,
                logger=None
            )
            
            final_movie.close()
            for clip in final_clips:
                clip.close()
                
            progress_bar.progress(1.0)
            status_text.markdown("### ✅ สร้างวิดีโอสำเร็จเรียบร้อยแล้ว!")
            detail_text.text("พร้อมให้รับชมและดาวน์โหลดด้านล่าง")
            return output_file
            
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการเรนเดอร์: {str(e)}")
            return None
    else:
        st.error("❌ ไม่สามารถสร้างวิดีโอได้")
        return None

# ==========================================
# 4. Execution
# ==========================================
if btn_generate:
    if not pexels_key:
        st.error("🔑 กรุณาใส่ Pexels API Key")
    elif not script_text.strip():
        st.error("📝 กรุณาใส่สคริปต์ก่อนครับ!")
    else:
        scenes_data = []
        for line in script_text.strip().split('\n'):
            if "|" in line:
                parts = line.split("|", 1)
                text = parts[0].strip()
                keyword = parts[1].strip()
                if text and keyword:
                    scenes_data.append({"text": text, "keyword": keyword})
        
        if not scenes_data:
            st.error("⚠️ รูปแบบสคริปต์ไม่ถูกต้อง")
        else:
            st.markdown("---")
            progress_bar = st.progress(0)
            status_text = st.empty()
            detail_text = st.empty()
            
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result_video = loop.run_until_complete(
                    process_video(scenes_data, pexels_key, voice_code, progress_bar, status_text, detail_text)
                )
                
                if result_video:
                    st.video(result_video)
                    with open(result_video, "rb") as file:
                        st.download_button(
                            label="⬇️ ดาวน์โหลดวิดีโอ (.mp4)",
                            data=file,
                            file_name=f"Smart_Auto_Video_{uuid.uuid4().hex[:4]}.mp4",
                            mime="video/mp4",
                            type="primary",
                            use_container_width=True
                        )
                    st.success("🎉 หากดาวน์โหลดเสร็จแล้ว คุณสามารถเคลียร์ข้อความสคริปต์และสร้าง Part ถัดไปได้เลย")
            except Exception as e:
                st.error(f"⚠️ ระบบเกิดขัดข้องฉุกเฉิน: {e}")
