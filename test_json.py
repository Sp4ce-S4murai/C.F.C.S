from flask import Flask, jsonify
app = Flask(__name__)
app.config["TESTING"] = True
client = app.test_client()

@app.route("/")
def test():
    return jsonify({"text": "\U0001f4f8 📸"})

print(client.get("/").get_data())
