from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import requests


ROOT = Path.cwd()
CURRENT_DIR = ROOT / "current"
STUDENT_REF_DIR = ROOT / "refs" / "student"
INSTRUCTOR_REF_DIR = ROOT / "refs" / "instructor" / "class_c_202607"
OUT_DIR = CURRENT_DIR / "generated-notes"

CODE_EXTENSIONS = {".c", ".cpp", ".h", ".hpp", ".txt", ".md"}
SKIP_DIRS = {".git", ".github", "generated-notes", "node_modules", ".vs", "Debug", "Release", "x64"}
MAX_FILE_CHARS = 12000
MAX_TOTAL_CHARS = 90000


def read_env(name: str, required: bool = True, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value or ""


def iter_source_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    files: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in CODE_EXTENSIONS:
            files.append(path)
    return sorted(files)


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="ignore")


def collect_code_context(base: Path, label: str) -> str:
    if not base.exists():
        return f"## {label}\n\n참고 코드 디렉터리를 찾지 못함.\n"

    chunks: list[str] = [f"## {label}\n"]
    total = 0
    for path in iter_source_files(base):
        rel = path.relative_to(base)
        text = read_text_file(path)
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n/* ... file truncated ... */\n"
        block = f"\n### FILE: {rel}\n\n```text\n{text}\n```\n"
        if total + len(block) > MAX_TOTAL_CHARS:
            chunks.append("\n... 추가 파일은 길이 제한으로 생략됨 ...\n")
            break
        chunks.append(block)
        total += len(block)
    return "".join(chunks)


def collect_comments(base: Path) -> str:
    lines: list[str] = []
    comment_re = re.compile(r"(//.*|/\*.*|\* .*|TODO.*|todo.*|놓친|미완성|나중|강사|확인)")
    for path in iter_source_files(base):
        rel = path.relative_to(base)
        text = read_text_file(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            if comment_re.search(line):
                lines.append(f"- {rel}:{idx}: {line.strip()}")
    if not lines:
        return "주석 메모를 찾지 못함."
    return "\n".join(lines[:200])


def collect_latest_commit_diff(base: Path) -> str:
    """Return only the changes introduced by the latest pushed commit."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(base),
                "diff",
                "--find-renames",
                "--unified=5",
                "HEAD^",
                "HEAD",
                "--",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return f"직전 커밋과 비교할 수 없음: {exc}"

    diff = result.stdout.strip()
    if not diff:
        return "이번 커밋에서 텍스트 코드 변경분을 찾지 못함."
    if len(diff) > MAX_TOTAL_CHARS:
        return diff[:MAX_TOTAL_CHARS] + "\n... 변경분 길이 제한으로 이후 내용 생략 ..."
    return diff


def build_prompt() -> str:
    repo = read_env("GITHUB_REPOSITORY", required=False, default="unknown/repo")
    sha = read_env("GITHUB_SHA", required=False, default="unknown")
    branch = read_env("GITHUB_REF_NAME", required=False, default="unknown")

    current_context = collect_code_context(CURRENT_DIR, "내 최신 코드")
    student_context = collect_code_context(STUDENT_REF_DIR, "우수 학생 참고 코드")
    instructor_context = collect_code_context(INSTRUCTOR_REF_DIR, "강사님 참고 코드")
    comment_context = collect_comments(CURRENT_DIR)
    latest_diff = collect_latest_commit_diff(CURRENT_DIR)

    return f"""
너는 C언어 수업 쉬는시간 정리노트를 만드는 튜터다.

목표:
- 직전 커밋(HEAD^)과 방금 push한 커밋(HEAD)의 차이를 기준으로 한 교시 정리노트를 만든다.
- 이번 push에서 새로 추가, 수정, 삭제된 내용만 노트의 중심으로 설명한다.
- 변경되지 않은 기존 코드는 변경분을 이해하는 데 꼭 필요한 경우에만 짧게 언급한다.
- 최신 코드 전체를 처음부터 다시 설명하지 않는다.
- 쉬는시간에 바로 읽고 다음 수업을 따라갈 수 있어야 한다.
- 최종 코드 전체 설명이 아니라 이번 교시에서 달라진 구현 흐름과 영향을 정리한다.
- 강사님/우수 학생 코드와 비교해서 부족한 부분을 제안한다.
- 참고 코드가 최신이 아니거나 관련 파일이 부족하면 "참고 코드 최신성 부족"을 표시한다.
- 내 코드가 미완성이면 "미완성 코드 있음"을 표시하고, 주석과 코드 흐름을 근거로 제안 코드를 작성한다.

문체:
- 한국어
- 초보자 기준
- "~이다"보다 "~임", "~하는 뜻", "~하기 위한 함수"처럼 정리
- 코드 실행 순서 중심
- 입력값 -> 처리 -> 결과 중심
- 배열은 [세로][가로] 기준으로 설명
- 쉬는시간용이므로 너무 길게 늘리지 말고, 바로 볼 수 있게 핵심 위주로 작성

반드시 포함할 섹션:
# C언어 쉬는시간 정리노트
## 0. 이번 교시 한 줄 요약
## 1. 이번 push에서 바뀐 내용
## 2. 새로 추가된 코드
## 3. 수정 또는 삭제된 코드
## 4. 변경 후 코드 흐름
## 5. 이번 변경에서 배운 C언어 개념
## 6. 강사님/우수 학생 코드와 비교
## 7. 미완성 코드 또는 놓친 부분
## 8. 다음 교시 시작 전 체크
## 9. 마지막 한 문장 복습

작성 규칙:
- 아래 `이번 push 변경분`의 `+` 줄과 `-` 줄을 최우선 근거로 사용한다.
- 변경된 파일명, 함수명, 변수명과 바뀐 동작을 구체적으로 적는다.
- 추가되지 않은 기존 기능을 이번에 배운 내용처럼 설명하지 않는다.
- 변경분이 작으면 노트도 짧게 작성한다. 분량을 채우려고 전체 코드를 반복 설명하지 않는다.

저장소 정보:
- repo: {repo}
- branch: {branch}
- sha: {sha}

내 코드 주석 메모:
{comment_context}

## 이번 push 변경분 (HEAD^ -> HEAD)

```diff
{latest_diff}
```

아래 최신 코드 전체는 변경분의 앞뒤 맥락을 확인할 때만 참고한다.

{current_context}

{student_context}

{instructor_context}
""".strip()


def call_openai(prompt: str) -> str:
    api_key = read_env("OPENAI_API_KEY")
    model = read_env("OPENAI_MODEL", required=False, default="gpt-4.1")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": prompt,
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    if "output_text" in data:
        return data["output_text"]

    texts: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                texts.append(content.get("text", ""))
    if texts:
        return "\n".join(texts)
    raise RuntimeError("OpenAI response did not contain text output.")


def flush_paragraph(lines: list[str], blocks: list[dict]) -> None:
    text = "\n".join(line for line in lines if line.strip()).strip()
    lines.clear()
    if text:
        blocks.append(notion_text_block("paragraph", text))


def notion_rich_text(text: str) -> list[dict]:
    chunks: list[dict] = []
    while text:
        part = text[:1900]
        text = text[1900:]
        chunks.append({"type": "text", "text": {"content": part}})
    return chunks or [{"type": "text", "text": {"content": ""}}]


def notion_text_block(kind: str, text: str) -> dict:
    return {
        "object": "block",
        "type": kind,
        kind: {"rich_text": notion_rich_text(text)},
    }


def markdown_to_notion_blocks(markdown: str) -> list[dict]:
    blocks: list[dict] = []
    paragraph: list[str] = []
    in_code = False
    code_lang = "plain text"
    code_lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_code:
                blocks.append(
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": notion_rich_text("\n".join(code_lines)),
                            "language": code_lang if code_lang in {"c", "cpp", "plain text", "text"} else "plain text",
                        },
                    }
                )
                code_lines.clear()
                in_code = False
                code_lang = "plain text"
            else:
                flush_paragraph(paragraph, blocks)
                in_code = True
                code_lang = line.strip("`").strip() or "plain text"
                if code_lang == "text":
                    code_lang = "plain text"
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            flush_paragraph(paragraph, blocks)
            continue

        if line.startswith("# "):
            flush_paragraph(paragraph, blocks)
            blocks.append(notion_text_block("heading_1", line[2:].strip()))
        elif line.startswith("## "):
            flush_paragraph(paragraph, blocks)
            blocks.append(notion_text_block("heading_2", line[3:].strip()))
        elif line.startswith("### "):
            flush_paragraph(paragraph, blocks)
            blocks.append(notion_text_block("heading_3", line[4:].strip()))
        elif line.startswith("> "):
            flush_paragraph(paragraph, blocks)
            blocks.append(notion_text_block("quote", line[2:].strip()))
        elif line.startswith("- "):
            flush_paragraph(paragraph, blocks)
            blocks.append(notion_text_block("bulleted_list_item", line[2:].strip()))
        elif re.match(r"^\d+\.\s+", line):
            flush_paragraph(paragraph, blocks)
            blocks.append(notion_text_block("numbered_list_item", re.sub(r"^\d+\.\s+", "", line).strip()))
        elif line.strip() == "---":
            flush_paragraph(paragraph, blocks)
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        else:
            paragraph.append(line)

    flush_paragraph(paragraph, blocks)
    return blocks[:95]


def upload_to_notion(markdown: str, title: str) -> str:
    token = read_env("NOTION_TOKEN")
    database_id = read_env("NOTION_PARENT_PAGE_ID")
    blocks = markdown_to_notion_blocks(markdown)
    lesson_date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        json={
            "parent": {"type": "database_id", "database_id": database_id},
            "properties": {
                "이름": {
                    "title": [{"type": "text", "text": {"content": title}}]
                },
                "수업 일시": {"date": {"start": lesson_date}},
            },
            "children": blocks,
        },
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(
            f"Notion API error {response.status_code}: {response.text}"
        )
    return response.json().get("url", "")


def extract_title_keyword(markdown: str) -> str:
    lines = [line.strip() for line in markdown.splitlines()]
    for index, line in enumerate(lines):
        if line.startswith("## 0."):
            for candidate in lines[index + 1:]:
                if candidate and not candidate.startswith("#"):
                    keyword = re.sub(r"[*_`>#]", "", candidate).strip()
                    return keyword[:45].rstrip(" .,;:-")
    return "이번 교시 핵심 내용"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    repo = read_env("GITHUB_REPOSITORY", required=False, default="unknown/repo").split("/")[-1]
    sha = read_env("GITHUB_SHA", required=False, default="unknown")
    short_sha = sha[:7] if sha != "unknown" else datetime.now(timezone.utc).strftime("%H%M%S")
    prompt = build_prompt()
    note = call_openai(prompt)
    keyword = extract_title_keyword(note)
    title = f"{repo} 쉬는시간 정리 - {keyword}"

    note_path = OUT_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{repo}_{short_sha}.md"
    note_path.write_text(note, encoding="utf-8")

    notion_url = upload_to_notion(note, title)
    print(json.dumps({"markdown": str(note_path), "notion_url": notion_url}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
