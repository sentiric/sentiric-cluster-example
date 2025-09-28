from flask import Flask
import os

app = Flask(__name__)
port = int(os.environ.get("PORT", 13024))

@app.route('/')
def signaling():
    return f"SIP Signaling running on port {port}\n"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)