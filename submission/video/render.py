"""Render a silent, under-three-minute storyboard using Pillow and FFmpeg."""
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
W, H = 1280, 720
font = 'C:/Windows/Fonts/segoeuib.ttf'
regular = 'C:/Windows/Fonts/segoeui.ttf'
big = ImageFont.truetype(font, 70)
mid = ImageFont.truetype(font, 30)
small = ImageFont.truetype(regular, 21)
scenes = [
 ('THE PROBLEM', 'WHEN AGENTS\nLOOP, SYSTEMS PAY.', 'One runaway agent can overwhelm tools.', 20),
 ('THE CONTROL PLANE', 'CONTAIN THE\nFAILURE.', 'Vaeltrixis intercepts supported agent requests.', 25),
 ('RUNTIME CONTAINMENT', 'ONE AGENT STOPS.\nOTHERS KEEP GOING.', 'Repeated calls trigger an isolated circuit.', 35),
 ('SELF-HOSTED FLAGSMITH', 'POLICY THAT\nACTUALLY ACTS.', 'Segments, flags and model routing drive decisions.', 30),
 ('POLICY REHEARSAL', 'TEST THE RULE\nBEFORE THE CHANGE.', 'Compare loop thresholds without executing tools.', 25),
 ('HUMAN RECOVERY', 'REVIEW. RELEASE.\nRESUME.', 'Release follows persisted control-plane refresh.', 25),
 ('OPEN SOURCE', 'YOUR AGENTS.\nYOUR CONTROL.', 'github.com/aravmittal123/Vaeltrixis', 14),
]


def frame(i, kicker, headline, sub):
    im = Image.new('RGB', (W, H), '#080f16')
    d = ImageDraw.Draw(im)
    for x in range(0, W, 80):
        d.line((x, 0, x, H), fill='#101e29', width=1)
    for y in range(0, H, 80):
        d.line((0, y, W, y), fill='#101e29', width=1)
    d.rounded_rectangle((58, 50, 1222, 666), radius=20, outline='#36504d', width=2)
    d.text((92, 82), 'V A E L T R I X I S', font=small, fill='#b8efab')
    d.text((92, 176), kicker, font=mid, fill='#94d9c6')
    d.multiline_text((92, 255), headline, font=big, fill='#f1f8f3', spacing=10)
    d.text((95, 525), sub, font=small, fill='#a6bdb7')
    d.line((95, 585, 340, 585), fill='#b8efab', width=4)
    if i in (1, 2, 3, 4, 5):
        d.rounded_rectangle((820, 175, 1130, 255), radius=12, outline='#9ce2b8', width=3)
        d.text((845, 195), 'AGENT', font=mid, fill='#d7f9dc')
        d.line((975, 255, 975, 320), fill='#8ae4d0', width=3)
        d.rounded_rectangle((820, 320, 1130, 400), radius=12, outline='#b8efab', width=3)
        d.text((845, 340), 'VAELTRIXIS', font=mid, fill='#d7f9dc')
        d.line((975, 400, 975, 465), fill='#8ae4d0', width=3)
        d.rounded_rectangle((820, 465, 1130, 545), radius=12, outline='#79b8c0', width=3)
        d.text((845, 485), 'FLAGSMITH', font=mid, fill='#b6e1e4')
    im.save(OUT / f'scene-{i}.png')


def main():
    segments = []
    for i, (k, h, s, duration) in enumerate(scenes):
        frame(i, k, h, s)
        segment = OUT / f'part-{i}.mp4'
        vf = (f"zoompan=z='min(zoom+0.00007,1.04)':d={duration*24}:s={W}x{H}:fps=24,"
              f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.5}:d=0.5,format=yuv420p")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loop', '1', '-i', str(OUT / f'scene-{i}.png'),
                        '-vf', vf, '-t', str(duration), '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-crf', '20', str(segment)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        segments.append(segment)
        print(f'Rendered scene {i+1}/{len(scenes)}', flush=True)
    playlist = OUT / 'segments.txt'
    playlist.write_text(''.join(f"file '{p.as_posix()}'\n" for p in segments), encoding='utf-8')
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-f', 'concat', '-safe', '0', '-i', str(playlist),
                    '-c', 'copy', '-movflags', '+faststart', str(OUT / 'vaeltrixis-silent.mp4')], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('Finished: 174 seconds, silent, 1280x720, 24 fps', flush=True)


if __name__ == '__main__':
    main()
