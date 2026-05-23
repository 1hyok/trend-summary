import concurrent.futures
import os
from collections import defaultdict
from typing import List, Literal

from google import genai
from pydantic import BaseModel

from src.collector import fetch_og_data


SYSTEM_PROMPT = """당신은 한국 트렌드 분석가입니다. 사용자가 다양한 한국 트렌드 소스(구글 트렌드, 유튜브 트렌딩, 한국 커뮤니티)에서 수집한 raw 데이터를 보여주면, 그 시점에 한국에서 뜨고 있는 주요 토픽을 식별하고 정리하세요.

지침:
- 여러 소스에서 반복되거나, 한 소스에서 강한 신호가 보이는 토픽을 우선합니다.
- 각 토픽에 2-3 문장의 자세한 설명을 제공합니다. 맥락, 배경, 왜 지금 뜨는지, 관련 인물/사건을 포함하세요. 한 줄 요약으로 끝내지 마세요.
- 각 토픽마다 그 토픽에 포함된 원본 게시글 제목을 3-5개 골라서 related_items에 원문 그대로 넣어주세요 (제목 끝의 게시판 prefix '모공' 등도 그대로).
- 카테고리는 다음 중 하나로 분류: 게임, 엔터, 정치, 사회, IT, 스포츠, 경제, 기타.
- 어느 소스(들)에서 신호가 잡혔는지 표시합니다.
- 의미 없는 노이즈(자동 생성된 광고, 스팸 등)는 제외합니다."""


class Topic(BaseModel):
    topic: str
    description: str
    category: Literal["게임", "엔터", "정치", "사회", "IT", "스포츠", "경제", "기타"]
    sources: List[str]
    related_items: List[str]


class TrendsResult(BaseModel):
    topics: List[Topic]


_MOCK_CATEGORY_BY_SOURCE = {
    "google_trends_kr": "기타",
    "theqoo": "엔터",
    "ruliweb": "게임",
    "dcinside_hit": "엔터",
    "namuwiki": "기타",
    "youtube_trending_kr": "엔터",
}


def _format_items(items):
    by_source = defaultdict(list)
    for item in items:
        by_source[item["source"]].append(item["title"])
    lines = []
    for source_name, titles in by_source.items():
        lines.append(f"\n[{source_name}]")
        for title in titles:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _mock_summary(items, max_topics):
    by_source = defaultdict(list)
    for item in items:
        by_source[item["source"]].append(item)

    sources = list(by_source.keys())
    indices = {s: 0 for s in sources}
    topics = []
    while len(topics) < max_topics:
        progress = False
        for src in sources:
            if indices[src] >= len(by_source[src]):
                continue
            item = by_source[src][indices[src]]
            related = [
                {
                    "title": by_source[src][i]["title"],
                    "url": by_source[src][i].get("url", ""),
                }
                for i in range(
                    indices[src], min(indices[src] + 3, len(by_source[src]))
                )
            ]
            indices[src] += 3
            progress = True
            topics.append(
                {
                    "topic": item["title"][:40],
                    "description": "(MOCK 모드: API 키 없어서 LLM 호출 안 함. UI 검증용 더미 응답입니다. 진짜 LLM은 2-3문장의 맥락/배경/관련 인물을 담아 더 풍부하게 설명합니다.)",
                    "category": _MOCK_CATEGORY_BY_SOURCE.get(item["source"], "기타"),
                    "sources": [item["source"]],
                    "related_items": related,
                    "image_url": "",
                }
            )
            if len(topics) >= max_topics:
                break
        if not progress:
            break
    return {"topics": topics}


def summarize(items, max_topics=10, model="gemini-2.5-flash"):
    if not items:
        return {"topics": []}
    if not os.environ.get("GOOGLE_API_KEY"):
        print("[summarizer] GOOGLE_API_KEY 없음 → mock 모드 (UI 검증용)")
        return _mock_summary(items, max_topics)

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    user_message = (
        f"다음은 방금 수집한 raw 데이터입니다:\n{_format_items(items)}\n\n"
        f"지금 한국에서 뜨고 있는 토픽을 최대 {max_topics}개로 정리해주세요."
    )

    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": TrendsResult,
        },
    )

    result = response.parsed.model_dump()
    # Attach URL to each related_item by matching title back to collector data
    for topic in result.get("topics", []):
        topic["related_items"] = [
            {"title": t, "url": _lookup_url(t, items)}
            for t in topic.get("related_items", [])
        ]
    _enrich_with_images(result.get("topics", []))
    return result


def _enrich_with_images(topics):
    """For each topic, fetch og:image of the first related_item URL. Parallel."""
    urls = []
    for topic in topics:
        url = ""
        for r in topic.get("related_items", []):
            u = r.get("url") if isinstance(r, dict) else ""
            if u:
                url = u
                break
        urls.append(url)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_og_data, url): i
            for i, url in enumerate(urls)
            if url
        }
        for future in concurrent.futures.as_completed(futures, timeout=15):
            i = futures[future]
            try:
                topics[i]["image_url"] = future.result().get("image", "")
            except Exception:
                topics[i]["image_url"] = ""

    for topic in topics:
        topic.setdefault("image_url", "")


def _lookup_url(title, items):
    if not title:
        return ""
    for it in items:
        if it["title"] == title:
            return it.get("url", "")
    # Loose match — LLM may have slightly altered whitespace
    norm = title.strip()
    for it in items:
        t = it["title"].strip()
        if t == norm or t in norm or norm in t:
            return it.get("url", "")
    return ""


if __name__ == "__main__":
    from dotenv import load_dotenv

    from src.collector import collect_all, load_config

    load_dotenv()
    config = load_config()
    items = collect_all()
    print(f"Collected {len(items)} items, calling LLM...")
    result = summarize(
        items,
        max_topics=config["summary"]["max_topics"],
        model=config["summary"]["llm_model"],
    )

    for topic in result["topics"]:
        print(f"\n[{topic['category']}] {topic['topic']}")
        print(f"  {topic['description']}")
        print(f"  Sources: {', '.join(topic['sources'])}")
