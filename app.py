import streamlit as st
import os
import asyncio
import requests
import edge_tts
import tempfile
import uuid
import gc
import subprocess

# ==========================================
# 1. ตั้งค่าพื้นฐาน Streamlit
# ==========================================
st.set_page_config(page_title="AI Auto Video Maker", page_icon="🎬", layout="wide")

WORK_DIR = tempfile.mkdtemp()

st.title("🎬 AI Auto Video Maker (Stable Version)")
st.markdown("โปรแกรมสร้างวิดีโออัตโนมัติจากสคริปต์ (ทำงานด้วย FFmpeg - ป้องกัน Error ได้ 100%)")
st.info("💡 **คำแนะนำ:** หากสคริปต์มีความยาวเกิน 5 บรรทัด แนะนำให้แบ่งทำทีละส่วน (Part)")

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
    st.markdown("- ใช้ภาษาอังกฤษ\n- หากค้นหาคลิปไม่เจอ ระบบจะข้ามฉากนั้นไป")

st.subheader("📝 ใส่สคริปต์ของคุณ")
default_script = """สวัสดีครับทุกคน ขอต้อนรับสู่ทริปอุซเบกิสถาน | uzbekistan
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
# 3. ฟังก์ชันหลักสำหรับประมวลผล (FFmpeg)
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
                # หาคุณภาพ HD
                hd_file = next((f for f in video_files if f['quality'] == 'hd' and f['height'] == 720), None)
                if not hd_file:
                     hd_file = video_files[0] 
                
                video_url = hd_file['link']
                vid_response = requests.get(video_url)
                with open(output_filename, 'wb') as f:
                    f.write(vid_response.content)
                return True
    except Exception as e:
        print(e)
    return False

async def generate_audio(text, output_filename, voice):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_filename)

def get_audio_duration(audio_path):
    # ใช้ ffprobe หาความยาวไฟล์เสียง
    cmd = ["ffprobe", "-i", audio_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    return float(result.stdout.strip())

def combine_audio_video(video_path, audio_path, output_path, duration):
    # รวมเสียงและภาพ และตัด/ค้างภาพให้พอดีกับความยาวเสียงเป๊ะๆ
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", video_path,  # ถ้าภาพสั้นกว่าเสียง ให้วนซ้ำ (loop)
        "-i", audio_path,
        "-t", str(duration),                     # ตัดเวลาให้เท่ากับความยาวเสียง
        "-c:v", "libx264", "-preset", "ultrafast", 
        "-c:a", "aac", "-strict", "experimental",
        "-pix_fmt", "yuv420p", "-vf", "scale=1280:720,setsar=1", # บังคับขนาดให้เท่ากันเพื่อกัน Error ตอนต่อคลิป
        "-map", "0:v:0", "-map", "1:a:0",        # เอาภาพจากไฟล์ที่ 0 เสียงจากไฟล์ที่ 1
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def concatenate_all_clips(clip_paths, final_output):
    # สร้างไฟล์ list.txt เพื่อให้ ffmpeg อ่านรายชื่อคลิปที่จะต่อกัน
    list_file = os.path.join(WORK_DIR, "list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for path in clip_paths:
            # ต้องใส่ 'file ' นำหน้าและครอบด้วย Single Quote
            safe_path = path.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
            
    # สั่งต่อคลิป
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",  # Copy เลยไม่ต้อง Render ใหม่ (เร็วมาก)
        final_output
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

async def process_video(scenes_data, api_key, voice, progress_bar, status_text, detail_text):
    final_clips = []
    total_scenes = len(scenes_data)
    
    for i, scene in enumerate(scenes_data):
        current_step = i + 1
        status_text.markdown(f"### 🎬 กำลังประมวลผลฉากที่ {current_step} จาก {total_scenes}")
        progress_bar.progress(i / (total_scenes + 1))
        
        unique_id = uuid.uuid4().hex[:6]
        audio_path = os.path.join(WORK_DIR, f"scene_{i}_{unique_id}.mp3")
        video_raw_path = os.path.join(WORK_DIR, f"scene_{i}_raw_{unique_id}.mp4")
        scene_output_path = os.path.join(WORK_DIR, f"scene_{i}_final_{unique_id}.mp4")
        
        detail_text.text(f"กำลังสร้างเสียง: \"{scene['text'][:30]}...\"")
        await generate_audio(scene["text"], audio_path, voice)
        
        detail_text.text(f"กำลังค้นหาคลิป: '{scene['keyword']}'")
        has_video = download_stock_video(scene["keyword"], video_raw_path, api_key)
        
        if has_video:
            detail_text.text(f"กำลังรวมร่างเสียงและภาพ...")
            try:
                # คำนวณความยาวเสียง
                audio_dur = get_audio_duration(audio_path)
                # รวมร่าง
                combine_audio_video(video_raw_path, audio_path, scene_output_path, audio_dur)
                final_clips.append(scene_output_path)
            except Exception as e:
                st.warning(f"⚠️ ฉากที่ {current_step}: รวมไฟล์ไม่สำเร็จ ({str(e)})")
        else:
            st.warning(f"⚠️ ฉากที่ {current_step}: ไม่พบวิดีโอสำหรับคำว่า '{scene['keyword']}'")
            
        gc.collect() 
        
    status_text.markdown("### ⚙️ กำลังต่อคลิปทั้งหมดเข้าด้วยกัน...")
    progress_bar.progress(total_scenes / (total_scenes + 1))
    
    if final_clips:
        output_file = os.path.join(WORK_DIR, f"AutoVideo_{uuid.uuid4().hex[:6]}.mp4")
        try:
            concatenate_all_clips(final_clips, output_file)
            
            progress_bar.progress(1.0)
            status_text.markdown("### ✅ สร้างวิดีโอสำเร็จเรียบร้อยแล้ว!")
            detail_text.text("พร้อมให้รับชมและดาวน์โหลด")
            return output_file
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการรวมคลิป: {str(e)}")
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
                
                if result_video and os.path.exists(result_video):
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
                    st.success("🎉 หากดาวน์โหลดเสร็จแล้ว คุณสามารถทำ Part ถัดไปได้เลย")
            except Exception as e:
                st.error(f"⚠️ ระบบเกิดขัดข้อง: {e}")
