from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from src.collector import collect_all, fetch_og_data, load_config
from src.summarizer import summarize

load_dotenv()
app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/trends")
def api_trends():
    config = load_config()
    items = collect_all()
    result = summarize(
        items,
        max_topics=config["summary"]["max_topics"],
        model=config["summary"]["llm_model"],
    )
    return jsonify(result)


@app.route("/api/preview")
def api_preview():
    url = request.args.get("url", "")
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "invalid url"}), 400
    return jsonify(fetch_og_data(url, timeout=5))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
