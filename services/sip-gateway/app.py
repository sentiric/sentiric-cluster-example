from flask import Flask
import os

app = Flask(__name__)
port = int(os.environ.get("PORT", 5060))

@app.route('/')
def gateway():
    return f"SIP Gateway running on port {port}\n"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)