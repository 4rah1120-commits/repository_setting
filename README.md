# C언어 쉬는시간 노트 자동화

## 선택한 방식

GitHub에 코드를 push하면 GitHub Actions가 자동 실행된다.

```text
GitHub push
-> 현재 저장소 코드 읽기
-> 강사님/우수 학생 저장소도 가능하면 같이 읽기
-> OpenAI API로 쉬는시간 정리노트 생성
-> Notion API로 페이지 생성
-> Markdown 파일도 Actions artifact로 저장
```

이 방식이면 매 교시 끝에 사용자는 평소처럼 GitHub에 push만 하면 된다.

---

## 한 번만 필요한 설정

GitHub 저장소의 `Settings -> Secrets and variables -> Actions`에 아래 값을 넣는다.

| 이름 | 의미 |
|---|---|
| `OPENAI_API_KEY` | 노트 생성을 위한 OpenAI API 키 |
| `NOTION_TOKEN` | Notion 통합 토큰 |
| `NOTION_PARENT_PAGE_ID` | 노트를 만들 상위 Notion 페이지 ID |

선택값:

| 이름 | 의미 |
|---|---|
| `OPENAI_MODEL` | 기본값 `gpt-4.1` |

---

## 저장소에 넣을 파일

수업용 GitHub 저장소에 아래 구조로 넣는다.

```text
.github/workflows/c-lesson-note.yml
scripts/generate_lesson_note.py
```

이 폴더에 있는 예시 파일을 그대로 복사하면 된다.

---

## Notion 권한

Notion에서 통합을 만든 뒤, 노트를 넣을 페이지에 해당 통합을 초대해야 한다.

```text
Notion 페이지 열기
-> 오른쪽 위 ...
-> Connections
-> 만든 통합 연결
```

이 작업은 Notion API가 페이지에 글을 쓰기 위해 필요하다.

---

## 자동 생성되는 노트 제목

```text
C언어 쉬는시간 정리노트 - 저장소명 - 커밋 앞 7자리
```

예:

```text
C언어 쉬는시간 정리노트 - pointer - a1b2c3d
```

---

## 참고 코드 최신성 처리

강사님/우수 학생 코드가 최신이 아니거나 읽히지 않으면 노트에 다음을 표시한다.

```text
참고 코드 최신성 부족
```

그 경우 내 코드의 주석과 현재 흐름을 기준으로 미완성 부분과 제안 코드를 작성한다.
