from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import yt_dlp
import os
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-key-for-local')

# Configure CORS based on environment
allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*')
CORS(app, resources={
    r"/api/*": {
        "origins": allowed_origins.split(','),
        "methods": ["POST", "OPTIONS"]
    }
})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/formats', methods=['POST'])
def get_formats():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided.'}), 400
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'http_headers': {
                'User-Agent': 'com.google.android.youtube/17.31.35 (Linux; U; Android 11) gzip',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Origin': 'https://m.youtube.com',
                'Referer': 'https://m.youtube.com/',
                'Connection': 'keep-alive',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'player_skip': ['webpage', 'config', 'js'],
                    'max_comments': 0,
                    'embed_webpage': False,
                    'hls_prefer_native': True,
                }
            },
            'socket_timeout': 15,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US'
        }

        def try_extract(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        # Try different methods
        info = None
        errors = []

        try:
            info = try_extract(ydl_opts)
        except Exception as e:
            errors.append(str(e))
            # Try with mobile client
            ydl_opts['http_headers']['User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/85.0.4183.109 Mobile/15E148 Safari/604.1'
            try:
                info = try_extract(ydl_opts)
            except Exception as e:
                errors.append(str(e))
                # Try with lower quality
                ydl_opts.update({
                    'format': 'best[height<=720]',
                    'player_client': ['tv_embedded', 'android']
                })
                try:
                    info = try_extract(ydl_opts)
                except Exception as e:
                    errors.append(str(e))
                    return jsonify({'error': f'Failed to fetch video: {"; ".join(errors)}'}), 400

        if not info or not info.get('formats'):
            return jsonify({'error': 'No formats available'}), 400

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
    except yt_dlp.utils.DownloadError as e:
        return jsonify({'error': f'Download error: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
