from flask import Flask, jsonify, request

import os
import sys

import monitor
import crop

N8N_DATA_DIR = "/Users/nino/Repository/n8n/data"

app = Flask(__name__)

@app.route('/crop', methods=['POST'])
def trigger_crop():
    DEFAULT_CAM = '260:180:0:298'
    DEFAULT_SCREEN = '323:442:249:26'

    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload provided"}), 400
            
        folder = data.get('folder')
        if not folder:
            return jsonify({"status": "error", "message": "Missing 'folder' in payload"}), 400

        target_dir = os.path.join(N8N_DATA_DIR, folder)
        if not os.path.exists(target_dir):
            return jsonify({"status": "error", "message": f"Target directory {target_dir} does not exist"}), 400
        
        crop.process(
            target_dir,
            data.get('cam_crop', DEFAULT_CAM),
            data.get('screen_crop', DEFAULT_SCREEN)
        )
        
        return jsonify({
            "status": "success", 
            "message": "Crop triggered in background.",
            "root_dir": target_dir
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/monitor', methods=['POST'])
def trigger_monitor():
    # Calling get_new_video with defaults (update_memory=True) triggers the download logic internal to monitor.py
    result = monitor.get_new_video()
    
    if not result:
        return jsonify({
             "status": "success", 
            "message": "No new content found."
        }), 200

    return jsonify({
        "status": "success", 
        "message": "Monitor check completed.",
        "result": result
    }), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    # Run on 0.0.0.0 to be accessible if needed, port 5000 default
    app.run(debug=True, host='0.0.0.0', port=8000)
