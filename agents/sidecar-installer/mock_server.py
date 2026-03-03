#!/usr/bin/env python3
from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/api/config/<node_id>')
def get_config(node_id):
    return jsonify({
        "server_url": "https://10.10.41.149:20005/node_mgmt/open_api/node",
        "api_token": "test-token-12345678",
        "node_id": node_id,
        "node_name": f"Test Node {node_id}",
        "zone_id": "1",
        "group_id": "1",
        "download_url": "",
        "install_dir": "C:\\fusion-collectors"
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    host = os.environ.get('SERVER_IP', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting mock server on {host}:{port}")
    app.run(host=host, port=port, debug=False)
