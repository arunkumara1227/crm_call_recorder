import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class VoiceTestController(http.Controller):

    @http.route('/wa_tracker/voice_test', auth='user', type='http', methods=['GET'])
    def voice_test_page(self, **kwargs):
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Voice Transcription Tester</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 700px; margin: 60px auto; padding: 20px; background: #f5f5f5; }
        h2 { color: #7c5cbf; }
        .card { background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
        .btn { padding: 14px 28px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; margin: 8px; transition: all 0.2s; }
        #recordBtn  { background: #7c5cbf; color: white; }
        #recordBtn.recording { background: #e74c3c; animation: pulse 1s infinite; }
        #stopBtn    { background: #e74c3c; color: white; display: none; }
        #testBtn    { background: #27ae60; color: white; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
        #status  { margin: 16px 0; padding: 12px; border-radius: 8px; background: #eef; font-size: 14px; min-height: 20px; }
        #result  { margin-top: 20px; padding: 16px; background: #f0fff0; border-radius: 8px; border-left: 4px solid #27ae60; display: none; }
        #result h4 { margin: 0 0 8px; color: #27ae60; }
        #resultText { font-size: 18px; color: #333; font-weight: bold; }
        #lang { font-size: 13px; color: #888; margin-top: 4px; }
        #translateBtn { background: #2980b9; color: white; margin-top: 10px; display: none; }
        #translationBox { margin-top: 12px; padding: 12px; background: #e8f4fd; border-radius: 8px; border-left: 4px solid #2980b9; display: none; }
        #translationBox h4 { margin: 0 0 6px; color: #2980b9; font-size: 14px; }
        #translationText { font-size: 17px; color: #222; font-weight: bold; }
        .timer { font-size: 24px; color: #e74c3c; font-weight: bold; display: none; }
        audio { width: 100%; margin: 12px 0; display: none; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🎤 Voice Transcription Tester</h2>
        <p style="color:#666">Record your voice and check if the AI can transcribe it correctly.</p>
        <hr>
        <div>
            <button class="btn" id="recordBtn" onclick="startRecording()">🎙️ Start Recording</button>
            <button class="btn" id="stopBtn"   onclick="stopRecording()">⏹ Stop</button>
        </div>
        <div class="timer" id="timer">⏺ <span id="seconds">0</span>s</div>
        <audio id="audioPlayer" controls></audio>
        <div id="status">Click "Start Recording" and speak into your microphone.</div>
        <button class="btn" id="testBtn" onclick="transcribe()" style="display:none">🔍 Transcribe Now</button>
        <div id="result">
            <h4>Transcription Result</h4>
            <div id="resultText"></div>
            <div id="lang"></div>
            <button class="btn" id="translateBtn" onclick="showTranslation()">🌐 Show English Translation</button>
            <div id="translationBox">
                <h4>English Translation</h4>
                <div id="translationText"></div>
            </div>
        </div>
    </div>

<script>
let mediaRecorder, audioChunks = [], timerInterval, elapsed = 0;

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.start();

        document.getElementById('recordBtn').textContent = '🔴 Recording...';
        document.getElementById('recordBtn').classList.add('recording');
        document.getElementById('stopBtn').style.display = 'inline-block';
        document.getElementById('testBtn').style.display = 'none';
        document.getElementById('result').style.display = 'none';
        document.getElementById('timer').style.display = 'block';
        document.getElementById('audioPlayer').style.display = 'none';

        elapsed = 0;
        timerInterval = setInterval(() => {
            elapsed++;
            document.getElementById('seconds').textContent = elapsed;
        }, 1000);

        setStatus('🎙️ Recording... speak now!', '#fff0f0');
    } catch(e) {
        setStatus('❌ Microphone access denied: ' + e.message, '#fff0f0');
    }
}

function stopRecording() {
    mediaRecorder.stop();
    clearInterval(timerInterval);
    document.getElementById('recordBtn').textContent = '🎙️ Start Recording';
    document.getElementById('recordBtn').classList.remove('recording');
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('timer').style.display = 'none';

    mediaRecorder.stream.getTracks().forEach(t => t.stop());

    mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        const url  = URL.createObjectURL(blob);
        const player = document.getElementById('audioPlayer');
        player.src = url;
        player.style.display = 'block';
        document.getElementById('testBtn').style.display = 'inline-block';
        setStatus('✅ Recording done (' + elapsed + 's). Play it back or click Transcribe.', '#f0fff0');
        window._audioBlob = blob;
    };
}

async function transcribe() {
    if (!window._audioBlob) { setStatus('No recording yet!', '#fff0f0'); return; }
    setStatus('⏳ Sending to AI... (first run downloads model ~150MB, may take 60s)', '#fffbe0');
    document.getElementById('testBtn').disabled = true;
    document.getElementById('result').style.display = 'none';

    const form = new FormData();
    form.append('audio', window._audioBlob, 'recording.webm');

    try {
        const resp = await fetch('/wa_tracker/voice_test/transcribe', {
            method: 'POST',
            body: form,
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const data = await resp.json();
        document.getElementById('testBtn').disabled = false;

        if (data.text) {
            document.getElementById('resultText').textContent = '"' + data.text + '"';
            document.getElementById('lang').textContent = 'Language: ' + data.language + ' | Duration: ' + data.duration + 's';
            document.getElementById('result').style.display = 'block';
            document.getElementById('translationBox').style.display = 'none';
            // Show translate button only if translation differs from original
            window._translation = data.translation || '';
            const showBtn = window._translation && window._translation !== data.text;
            document.getElementById('translateBtn').style.display = showBtn ? 'inline-block' : 'none';
            document.getElementById('translateBtn').textContent = '🌐 Show English Translation';
            setStatus('✅ Transcription complete!', '#f0fff0');
        } else {
            setStatus('⚠️ No speech detected or transcription failed. Error: ' + (data.error || 'empty result'), '#fff0f0');
        }
    } catch(e) {
        document.getElementById('testBtn').disabled = false;
        setStatus('❌ Error: ' + e.message, '#fff0f0');
    }
}

function showTranslation() {
    const box = document.getElementById('translationBox');
    const btn = document.getElementById('translateBtn');
    if (box.style.display === 'none') {
        document.getElementById('translationText').textContent = '"' + window._translation + '"';
        box.style.display = 'block';
        btn.textContent = '🌐 Hide Translation';
    } else {
        box.style.display = 'none';
        btn.textContent = '🌐 Show English Translation';
    }
}

function setStatus(msg, bg) {
    const el = document.getElementById('status');
    el.textContent = msg;
    el.style.background = bg || '#eef';
}
</script>
</body>
</html>"""
        return html

    @http.route('/wa_tracker/voice_test/transcribe', auth='user', type='http', methods=['POST'], csrf=False)
    def voice_test_transcribe(self, audio=None, **kwargs):
        try:
            if not audio:
                return request.make_response(
                    json.dumps({'error': 'No audio received'}),
                    headers=[('Content-Type', 'application/json')]
                )

            audio_bytes = audio.read()
            _logger.info("Voice test: received %d bytes of audio", len(audio_bytes))

            from odoo.addons.whatsapp_neonize.models.voice_utils import transcribe_audio
            result = transcribe_audio(audio_bytes, env=request.env)

            _logger.info("Voice test result: %s", result)
            return request.make_response(
                json.dumps(result),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            _logger.error("Voice test error: %s", e, exc_info=True)
            return request.make_response(
                json.dumps({'text': '', 'language': 'unknown', 'duration': 0.0, 'error': str(e)}),
                headers=[('Content-Type', 'application/json')]
            )
