# 한국 트렌드 수집·요약 실험

Google Trends, YouTube, 한국 커뮤니티 등 설정된 소스에서 항목을 모아 요약하는 로컬 Flask 앱입니다.

## 실행

Python 환경에서 의존성을 설치하고 `.env.example`을 복사해 API 키를 설정하세요. `GOOGLE_API_KEY`는 Gemini 요약에 필요하며, `YOUTUBE_API_KEY`가 없으면 YouTube 소스를 건너뜁니다.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

앱은 `http://127.0.0.1:8000`에서 로컬로 실행됩니다. 수집 소스는 `config.yaml`에서 조정할 수 있습니다.

## 상태

개인 실험용 프로젝트입니다. 실제 실행 여부는 로컬 API 키와 각 수집 소스의 현재 응답에 따라 달라집니다.
