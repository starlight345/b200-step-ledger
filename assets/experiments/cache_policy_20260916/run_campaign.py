import csv,json,os,pathlib,subprocess,threading,time

root=pathlib.Path(__file__).resolve().parent
fields='index,uuid,memory.used,utilization.gpu,power.draw,clocks.sm,clocks.mem,temperature.gpu'
def snapshot():
 p=subprocess.run(['nvidia-smi','-i','1','--query-gpu='+fields,'--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
 return {'time_unix':time.time(),'raw':p.stdout.strip(),'error':p.stderr.strip(),'exit':p.returncode}
initial=snapshot();(root/'campaign-start.json').write_text(json.dumps(initial,indent=2))
parts=next(csv.reader([initial['raw']]))
if int(parts[2].strip())>100 or int(parts[3].strip())>0:raise RuntimeError('GPU1 no longer idle: '+initial['raw'])
stop=threading.Event()
def monitor():
 with (root/'telemetry.jsonl').open('w') as f:
  while not stop.is_set():
   try:f.write(json.dumps(snapshot())+'\n');f.flush()
   except Exception as e:f.write(json.dumps({'error':str(e),'time_unix':time.time()})+'\n');f.flush()
   stop.wait(.5)
t=threading.Thread(target=monitor,daemon=True);t.start()
env=dict(os.environ,CUDA_VISIBLE_DEVICES='1')
try:
 with (root/'campaign.jsonl').open('w') as out,(root/'campaign.err').open('w') as err:
  result=subprocess.run([str(root/'cache_probe')],cwd=root,env=env,stdout=out,stderr=err,timeout=300)
 (root/'campaign-complete.json').write_text(json.dumps({'returncode':result.returncode,'time_unix':time.time()},indent=2))
 if result.returncode:raise RuntimeError('benchmark exit '+str(result.returncode))
finally:stop.set();t.join(timeout=10)
print('CAMPAIGN_COMPLETE',flush=True)
