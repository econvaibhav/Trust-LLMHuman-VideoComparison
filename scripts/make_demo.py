#!/usr/bin/env python3
"""Regenerate fictional demo clips. Requires Pillow, FFmpeg and DejaVu fonts.
Run from a development checkout before starting a study; it updates bundled assets.
"""
from pathlib import Path
import json,subprocess,hashlib,sys
from PIL import Image,ImageDraw,ImageFont
r=Path(__file__).resolve().parents[1]
(r/'data/demo-assets').mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(r))
from videotrust.common import write_json,file_hash,digest
from videotrust.__main__ import study_config
asset=r/'videotrust/demo'; (asset/'media').mkdir(parents=True,exist_ok=True)
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'; bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
items=[('demo_community','A new community garden','A neighborhood post','The town plans to turn an empty lot\ninto a community garden.','The post includes a meeting date\nand a link to the published plan.',7.5),('demo_miracle','A remarkable daily habit','A wellness creator','One simple habit can improve\nyour entire life in just a week.','The creator shares a personal story.\nNo independent evidence is provided.',3.0),('demo_transport','A change to the bus route','A commuter update','The 24 bus will take a different\nroute from next Monday.','The post shows a route sketch.\nIt does not name the source.',5.5)]
catalog=[]; analyses=[]
for i,(vid,title,tag,claim,context,score) in enumerate(items):
 frames=[]
 for j,text in enumerate((claim,context)):
  im=Image.new('RGB',(960,540),'#132e2a');d=ImageDraw.Draw(im)
  d.rounded_rectangle((45,40,915,500),18,fill=['#234e43','#29423b'][j])
  d.text((80,75),'FICTIONAL DEMO CLIP  /  '+str(i+1).zfill(2),font=ImageFont.truetype(bold,15),fill='#c6d2be')
  d.text((80,143),tag,font=ImageFont.truetype(font,23),fill='#dbad84')
  d.multiline_text((80,216),text,font=ImageFont.truetype(font,30),fill='#fffbee',spacing=15)
  d.text((80,442),'VIDEO TRUST LAB     •     SILENT DEMONSTRATION',font=ImageFont.truetype(font,13),fill='#bdcbb8')
  d.rounded_rectangle((80,391,835,395),2,fill='#668576');d.rounded_rectangle((80,391,80+int(755*(j+1)/2),395),2,fill='#d99a72')
  tmp=r/'data/demo-assets'/f'{vid}_{j}.png';im.save(tmp);frames.append(tmp)
 target=asset/'media'/f'{vid}.mp4'
 subprocess.run(['ffmpeg','-loglevel','error','-y','-loop','1','-t','4','-i',str(frames[0]),'-loop','1','-t','4','-i',str(frames[1]),'-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-t','8','-r','24','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],check=True)
 catalog.append({'video_id':vid,'title':title,'media_path':f'media/{vid}.mp4','media_sha256':file_hash(target),'metadata':{},'comments':[],'is_demo':True})
 for repeat,delta in [(1,-.5),(2,.5)]:
  analyses.append({'video_id':vid,'job_id':digest([vid,repeat]),'model':'synthetic-demo','temperature':0,'repeat':repeat,'evidence_mode':'demo_fixture','prompt_version':'demo-v1','is_demo':True,'status':'ok','trust_score':score+delta,'rationale':['The fictional claim names a meeting and a published plan; these are possible verification cues, though the plan has not been checked.','The fictional claim is broad and uses a personal anecdote without supporting evidence.','The fictional post provides a concrete change, but the original source is missing.'][i],'factors':['Demonstration only'],'full_summary':claim.replace('\n',' '),'short_summary':title,'limitations':['Hand-written score for testing the interface. No model was called.']})
write_json(asset/'catalog.json',catalog);write_json(asset/'study.json',study_config(3,True))
(asset/'analyses.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in analyses))
print('Created 3 original demo clips and 6 explicitly synthetic model records.')
