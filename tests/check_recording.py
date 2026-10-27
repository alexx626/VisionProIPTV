"""Real FFmpeg recording and ffprobe validation; isolated settings and local input."""
import os
import sys
import json
import subprocess
import tempfile
import socket
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
scratch = tempfile.TemporaryDirectory()
os.environ['APPDATA'] = scratch.name
from PyQt5 import QtCore
from player_services import Recorder, settings

ffmpeg, ffprobe = sys.argv[1:3]
root = Path(scratch.name)
source = root / 'source.ts'
subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=25',
                '-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=48000', '-t', '5',
                '-c:v', 'mpeg2video', '-c:a', 'mp2', str(source)], check=True)
app = QtCore.QCoreApplication([])
cfg = settings()
cfg.setValue('Settings/ffmpeg_path', ffmpeg)
cfg.setValue('Settings/record_dir', str(root / 'recordings'))
cfg.setValue('Settings/auto_remux', False)
cfg.sync()

def run(container, url):
    cfg.setValue('Settings/record_format', container)
    cfg.sync()
    recorder = Recorder()
    states = []
    recorder.changed.connect(lambda state, detail: states.append(state))
    loop = QtCore.QEventLoop()
    recorder.finished.connect(loop.quit)
    guard = QtCore.QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(loop.quit)
    guard.start(15000)
    recorder.start(url, 'Test / Channel')
    loop.exec_()
    assert not recorder.active, 'Recording did not finish'
    return recorder, states

for container in ('ts', 'mkv'):
    recorder, states = run(container, str(source))
    assert states[-1] == 'saved', states
    result = subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(recorder.output)])
    data = json.loads(result)
    assert {s['codec_name'] for s in data['streams']} == {'mpeg2video', 'mp2'}
    assert 4.5 <= float(data['format']['duration']) <= 5.5
    print('PASS:', container, 'valid audio/video, original codecs, duration', data['format']['duration'])
recorder, states = run('ts', str(root / 'missing.ts'))
assert states[-1] == 'error', states
cfg.setValue('Settings/ffmpeg_path', str(root / 'missing.exe'))
cfg.sync()
print('PASS: invalid source produces error, no false success')

# Pace a local fixture through real FFmpeg so Stop Rec is tested without network.
from unittest.mock import patch
cfg.setValue('Settings/ffmpeg_path', ffmpeg)
cfg.setValue('Settings/record_format', 'ts')
cfg.sync()
recorder = Recorder()
states = []
loop = QtCore.QEventLoop()
def changed(state, detail):
    states.append(state)
    if state == 'recording':
        QtCore.QTimer.singleShot(1500, recorder.stop)
recorder.changed.connect(changed)
recorder.finished.connect(loop.quit)
guard = QtCore.QTimer()
guard.setSingleShot(True)
guard.timeout.connect(loop.quit)
guard.start(20000)
original_start = QtCore.QProcess.start
def paced_start(process, program, args):
    i = args.index('-i')
    original_start(process, program, args[:i] + ['-re', '-stream_loop', '-1'] + args[i:])
with patch.object(QtCore.QProcess, 'start', paced_start):
    recorder.start(str(source), 'Live fixture')
loop.exec_()
assert not recorder.active and states[-1] == 'saved' and 'stopping' in states, states
data = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_format', '-of', 'json', str(recorder.output)]))
assert float(data['format']['duration']) > 1
print('PASS: paced capture, graceful Stop Rec, playable finalized output')

# A compatible live-TV fixture must become MP4 only after successful finalization.
mp4_source = root / 'h264.ts'
subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=320x180:rate=25',
                '-f', 'lavfi', '-i', 'sine=frequency=500:sample_rate=48000', '-t', '5',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(mp4_source)], check=True)
cfg.setValue('Settings/auto_remux', True)
cfg.setValue('Settings/record_duration', 'custom')
cfg.setValue('Settings/record_hours', 0)
cfg.setValue('Settings/record_minutes', 0)
cfg.setValue('Settings/record_seconds', 2)
cfg.sync()
recorder, states = run('ts', str(mp4_source))
assert states[-1] == 'saved' and 'remuxing' in states, states
assert recorder.output.suffix == '.mp4'
assert not recorder._original.exists(), 'Intermediate should be removed only after success'
data = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(recorder.output)]))
assert {s['codec_name'] for s in data['streams']} == {'h264', 'aac'}
assert 1.8 <= float(data['format']['duration']) < 2.5
assert recorder.elapsed_seconds >= 1.8
print('PASS: custom 2-second automatic stop, progress, MP4 h264/aac, source removed after successful remux')

# Force a remux-only failure, keeping the finished original recoverable.
original_start = QtCore.QProcess.start
def reject_mp4(process, program, args):
    if str(args[-1]).endswith('.mp4'):
        args = ['-this-option-does-not-exist']
    original_start(process, program, args)
with patch.object(QtCore.QProcess, 'start', reject_mp4):
    recorder, states = run('ts', str(mp4_source))
assert states[-1] == 'error' and recorder.output.suffix == '.ts'
assert recorder.output.exists() and recorder.output.stat().st_size > 0
print('PASS: MP4 failure preserves original; no false saved notification')
