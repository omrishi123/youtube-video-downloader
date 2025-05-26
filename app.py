from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import yt_dlp
import os

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
            'skip_download': True,
            'format': 'bestvideo+bestaudio/best',  # Changed format string
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        video_formats = []
        audio_formats = []
        combined_formats = []

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
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
