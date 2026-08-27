# Benchmark: js-xray vs raw file

에이전트가 난독화된 JavaScript를 분석할 때 js-xray 파이프라인이 얼마나 효과적인지 측정한 결과입니다.

## 실험 설계

**대상 파일**: 28 KB, 1줄짜리 강난독화 파일 (RC4 문자열 배열 + 제어흐름 평탄화 + self-defending)

**모델**: claude-sonnet-5 via algorix-relay

**과제**: 난독화된 JS 안에서 `sign(input, salt)` 함수를 찾아 Python으로 재구현하고, 13개 테스트 케이스(빈 문자열·ASCII·이모지·서로게이트·한글 등)를 통과시킬 것

### 조건 (Arm)

| | A | B | C |
|---|---|---|---|
| 난독화 파일 | ✅ | ✅ | ✅ |
| .xrayjs 산출물 | ❌ | ✅ | ✅ |
| xq CLI 허용 | ❌ | ✅ | ✅ |
| js-xray 스킬 로드 | ❌ | ❌ | ✅ |

---

## 결과

| 지표 | A: raw 파일만 | B: xrayjs + xq | C: xrayjs + xq + 스킬 |
|---|---:|---:|---:|
| 정확도 | 13/13 | 13/13 | 13/13 |
| **wall time** | **16분 5초** | **6분 50초** | 5분 56초 |
| **총 토큰** | **8,920,677** | **2,273,771** | 2,478,064 |
| 총 input 토큰 | 8,878,956 | 2,255,304 | 2,459,701 |
| 총 output 토큰 | 41,721 | 18,467 | 18,363 |
| 피크 컨텍스트 (단일 턴) | 162,008 | 74,273 | 83,160 |
| 툴 호출 수 | 89 | 44 | 44 |
| xq 사용 횟수 | 0 | 5 | 4 |
| 구현 시작 시점 | call #76 | call #9 | call #12 |

### 비용 (Claude Sonnet 5 공식 기준: input $2/MTok, output $10/MTok)

| | A | B | C |
|---|---:|---:|---:|
| input 비용 | $17.76 | $4.51 | $4.92 |
| output 비용 | $0.42 | $0.18 | $0.18 |
| **합계** | **$18.18** | **$4.70** | **$5.10** |

**A → B 기준: 한 번 실행에 $13.48 절감 (74% 저렴)**

---

## 해석

### 왜 A가 이렇게 비싼가

A 조건의 에이전트는 28 KB 난독화 파일을 `sed`로 페이지 넘기며 **74번 bash**를 썼습니다.
매 턴마다 컨텍스트가 불어나고, 90턴 내내 그 컨텍스트를 들고 돌았습니다.
구현을 시작한 건 **call #76** — 거의 마지막에서야 알고리즘을 파악했습니다.

B 조건에서는 xq로 **5번 질문**하고 **call #9**에 구현을 시작했습니다.

### B가 C보다 살짝 나은 이유

스킬 문서 자체를 읽는 비용이 추가됩니다. xrayjs 산출물이 충분히 잘 정리돼 있으면
스킬 없이도 에이전트가 알아서 xq를 활용합니다.

---

## 파이프라인: 분석 순서

```
입력 .js
   │
   ▼ 1. deobfuscate (WebCrack)
   │   · RC4/base64 문자열 배열 디코딩
   │   · 난독화 패턴 제거
   │   → webcrack.js
   │
   ▼ 2. inline (Babel AST)
   │   · WebCrack이 놓친 per-IIFE-scope 문자열 배열 처리
   │   · 파싱 실패 시 자동 롤백
   │   → inline.js
   │
   ▼ 3. deflatten (Babel AST)
   │   · 항상-참/거짓 분기 제거 (dead branch elimination)
   │   · switch 시퀀스 선형화 ("2|0|1".split("|") 패턴)
   │   · 순수 call forwarder 인라인 (S.fn(fetch,url) → fetch(url))
   │   · 안전하게 증명 못 하면 건드리지 않음
   │   → clean.js
   │
   ▼ 4. structure (AST 사실 추출)
   │   · 함수 목록, 호출 그래프, 클래스, URL
   │   → structure.json
   │
   ▼ 5. explain (역할·플로우 추론)
   │   · 진입점, 실행 흐름, 함수 역할 + 근거
   │   · 알고리즘 탐지 (FNV-1a, murmur3, …)
   │   · 네트워크 계약, 포팅 스펙
   │   → xray.json
   │
   ▼ 6. anchors (키워드 그렙)
   │   · hashing/crypto, network, fingerprinting 등 카테고리 태깅
   │   → analysis.json
   │
   ▼ 7. report (Markdown)
   │   → report.md (사람이 읽는 버전)
   │
   ▼ 8. TOON 인코딩
       · xray.json을 토큰 절약형 포맷으로 변환
       → xray.toon, toon_stats.json
```

### xq: 산출물에 좁은 질문 던지기

전체 xray.json을 컨텍스트에 올리는 대신, 필요한 부분만 뽑아씁니다.

```bash
xq summary              # 파일 개요 (몇백 토큰)
xq find hash            # "hash"가 들어간 함수 목록
xq show signData        # 함수 하나: xray.json 항목 + clean.js 소스
xq callers signData     # 누가 이 함수를 부르나
xq callees signData     # 이 함수가 무엇을 부르나
xq flow signData        # 실행 흐름
xq port --all           # 포팅 스펙 (Python 재구현 가이드)
xq roles hashing        # 역할별 함수 목록
xq grep fetch           # clean.js에서 텍스트 검색
xq entries              # 진입점 목록
```

`show` 하나가 xray.json 전체 대비 **54배 작고**, `grep`은 **600배 작습니다**.

---

## 재현 방법

```bash
# 파이프라인 실행 (산출물 생성)
python3 skill/scripts/xray.py target.js

# 각 조건 실행 (pi CLI 필요)
cd /tmp/pib4/A && pi --provider opencodex --model algorix-relay/claude-sonnet-5 \
  --mode json --no-session "\$(cat prompt.txt)" > run.jsonl 2> err.txt

cd /tmp/pib4/B && pi --provider opencodex --model algorix-relay/claude-sonnet-5 \
  --mode json --no-session "\$(cat prompt.txt)" > run.jsonl 2> err.txt

# 스코어링
python3 /tmp/pib4/score.py
```

