from flask import Flask, render_template, request, jsonify, make_response
from flask_cors import CORS
import yt_dlp
import os
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Match Railway environment variables
app.config.update(
    SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', '[generate-a-random-string]'),
    ENV=os.environ.get('FLASK_ENV', 'production'),
    ALLOWED_ORIGINS=os.environ.get('ALLOWED_ORIGINS', 'https://youtube-video-downloader-production-8a13.up.railway.app/')
)

# Configure CORS for Railway
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Allow all origins temporarily for debugging
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self' https: 'unsafe-inline' 'unsafe-eval'; img-src 'self' https: data:; media-src 'self' https: blob:;"
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/formats', methods=['POST'])
def get_formats():
    # Add OPTIONS handler
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response

    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided.'}), 400
    try:
        base_opts = {
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,
            'nocheckcertificate': True,
            'extract_flat': False,
            'no_call_home': True,
            'geo_bypass': True,
            'socket_timeout': 30,
            'format': 'best',
            'legacy_server_connect': True,  # Important for Railway
        }

        # Railway-specific configurations
        configs = [
            {
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                },
                'extractor_args': {'youtube': {
                    'player_client': ['web'],
                    'player_skip': [],
                }}
            },
        ]

        info = None
        last_error = None

        # Try each configuration and log attempts
        for i, config in enumerate(configs):
            try:
                logger.info(f"Trying config {i+1}")
                ydl_opts = {**base_opts, **config}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                if info and info.get('formats'):
                    logger.info("Successfully extracted video info")
                    break
            except Exception as e:
                last_error = str(e)
                logger.error(f"Config {i+1} failed: {last_error}")
                continue

        if not info or not info.get('formats'):
            return jsonify({'error': f'Could not extract video info: {last_error}'}), 400

        video_formats = []
        audio_formats = []
        combined_formats = []

        if not info.get('formats'):
            return jsonify({'error': 'No formats available for this video'}), 400

        for f in info.get('formats', []):
            if not f.get('url'):
                continue
                
            format_info = {
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'filesize': f.get('filesize') or f.get('filesize_approx'),
                'url': f.get('url'),
                'vcodec': f.get('vcodec'),
                'acodec': f.get('acodec'),
            }
            
            # Add quality info
            if f.get('height'):
                format_info['quality'] = f"{f.get('height')}p"
            elif f.get('format_note'):
                format_info['quality'] = f.get('format_note')
            else:
                format_info['quality'] = 'N/A'
                
            # Add bitrate for audio
            if f.get('abr'):
                format_info['bitrate'] = f"{int(f.get('abr'))}kbps"
            
            # Categorize formats
            if f.get('format_note') and 'DASH' in f.get('format_note'):
                # Handle DASH formats
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    combined_formats.append(format_info)
            elif '+' in f.get('format_id', ''):
                # Handle merged formats
                combined_formats.append(format_info)
            elif f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                combined_formats.append(format_info)
            elif f.get('vcodec') != 'none':
                video_formats.append(format_info)
            elif f.get('acodec') != 'none':
                audio_formats.append(format_info)

        # Sort formats by quality
        video_formats.sort(key=lambda x: int(x['quality'].replace('p', '')) if x['quality'].replace('p', '').isdigit() else 0, reverse=True)
        audio_formats.sort(key=lambda x: int(x.get('bitrate', '0').replace('kbps', '')) if x.get('bitrate', '0').replace('kbps', '').isdigit() else 0, reverse=True)
        combined_formats.sort(key=lambda x: int(x['quality'].replace('p', '')) if x['quality'].replace('p', '').isdigit() else 0, reverse=True)

        return jsonify({
            'title': info.get('title'),
            'thumbnail': info.get('thumbnail'),
            'formats': {
                'combined': combined_formats,
                'video_only': video_formats,
                'audio_only': audio_formats
            }
        })
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))  # Railway uses port 10000
    app.run(host='0.0.0.0', port=port)
