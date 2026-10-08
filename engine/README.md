# engine — worldengine

World Platform의 **경험 런타임**(SPEC.md v0.4 §XR). 장면 JSON 하나 → 링크로 여는 three.js 3D 페이지 · 헤드리스 PNG · (선택) 2D 평면.
게임 엔진으로 키워 가는 중이다 (런타임 모듈 분리 · 모바일/데스크톱 조작 · 관절체 · 그리는 로봇 순).

## 두 렌더러

| | `worldengine/html.py` (legacy) | `runtime/` (게임 엔진 런타임) |
|---|---|---|
| 입력 | render3d 장면 (매장 상자 유형) | **world/1** JSON (`worlds/*.world.json`) — 엔티티 · 재질 · 행동 · 시점 · 플레이어 |
| 구조 | HTML 파일 하나에 전부 | ES 모듈: `engine.js` · `world.js` · `materials.js` · `registry.js` · `plugins/` · `controls/` · `ui/` |
| 조작 | 궤도 회전 | **둘러보기**(궤도, 한 손가락 회전 · 두 손가락 확대) / **걷기**(WASD·드래그 · 휴대폰 가상 조이스틱) · 아이 1.1 m / 어른 1.7 m 눈높이 · 충돌 |
| 확장 | 코드 수정 | 플러그인이 엔티티 유형·행동·재질 테마를 등록. 코어는 유형 이름을 모른다 |

런타임 코어 플러그인 `core`: box · cylinder · cone · sphere · capsule · torus · plane · ground · text · light · terrain · path · person · arch, 행동 spin · bob · orbit.
`retail` 플러그인: 옛 매장 장면 전체를 `retail.store` 엔티티 하나로 그린다 (노란 강조색은 이 플러그인의 테마 — 세계가 `retail.accent` 로 덮어쓸 수 있다).

좌표: 미터, z 위, x 동, y 북. three.js 의 y-위로 바꾸는 곳은 `engine.js` 의 root 그룹 한 곳뿐.

## 출처

`cogito5170/se_new@02e87d5` 의 `render3d/`(gentle_monster 3D 도구)에서 가져왔다. 패키지 이름만 `render3d` → `worldengine` 로 바꿨다.

| 가져온 것 | 바뀐 점 |
|---|---|
| `scene.py` 장면 형식 + `check()` | 그대로 |
| `layout.py`, `examples/` (홍대 매장 층별, 매장 모듈 AS-IS/TO-BE) | 그대로 — 대조용 기준 세계 |
| `html.py` three.js r170 PBR 페이지 | 나무 모양 상수를 `shapes.py` 로 분리 (원래 SAR `visibility.py` 에 의존) |
| `headless.py` | 다시 씀: playwright 가 없으면 **Chromium CLI** 로 렌더, three.js 는 **저장소에 벤더링한 사본**에서 서빙 (CDN 차단 환경에서도 동작) |
| `pipeline.py` | matplotlib 이 없으면 평면/대체 3D 를 "없음 + 이유"로 기록 (그림이 없는데 있다고 하지 않는다) |
| `plan.py`, `mpl3d.py`, `fog.py` | 그대로 (matplotlib 은 선택 의존성) |

**가져오지 않은 것**: `vv*.py`, `sar_bridge.py`, `scene3d_ab.py`, `mission_anim.py`, `visibility.py` — SAR 임무 검증 전용이고 `sar/` 패키지 전체에 의존한다. CLI 의 `vv/sar/ab/anim` 명령도 함께 뺐다.

## 쓰기

```bash
cd engine
python3 -m worldengine example --list
python3 -m worldengine example hongdae/F1 --views aerial,eye      # → build/hongdae_F1.{html,md,_aerial.png,_eye.png}
python3 -m worldengine layout my_layout.json --key F1 --no-browser
python3 -m worldengine world worlds/contradiction_garden.world.json --views aerial,eye     # 런타임으로 렌더
python3 -m worldengine world example:hongdae/F1 --mode walk --eye child                    # 옛 매장을 아이 눈높이로
python3 -m worldengine serve            # 같은 와이파이의 휴대폰에서 열 주소를 찍어 준다
python3 -m unittest discover -s tests -v   # node 가 있으면 runtime/tests/*.test.mjs 도 함께 돈다
```

보고의 `백엔드:` 줄이 각 그림을 실제로 무엇이 그렸는지 말한다: `three.js r170 · headless chromium (CLI|playwright)` / `matplotlib 대체(비실사)` / `없음`.

## 헤드리스 렌더 (브라우저 찾는 순서)

1. `WE_CHROMIUM` 환경변수
2. `/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell` — 뷰포트가 `--window-size` 와 정확히 같다
3. `/opt/pw-browsers/chromium-*/chrome-linux/chrome` — `--headless=new` 에서 아래쪽에 빈 띠가 생긴 적이 있다 (테스트가 잡는다)
4. PATH 의 `chromium` / `chromium-browser` / `google-chrome`

페이지는 `window.__done` / `window.__err` 로 상태를 알리고, 서빙할 때 넣는 작은 스크립트가 이를 `console.log("WE_STATUS:...")` 로 바꿔 stderr 에서 읽는다. 오류 페이지는 스크린샷을 성공으로 내지 않는다.

## 측정된 것 (이 저장소 환경, 2026-10-08)

런타임 (`tests/test_runtime.py`, 실제 headless Chromium 안에서 실제 이벤트 처리기로 측정):

| 항목 | 기대 | 측정 |
|---|---|---|
| 조이스틱 40 px 위로, 1 s (휴대폰 390×844) | 1.4 m/s × 0.675 = 0.9455 m | 0.9455 m, 진행 방향 이탈 0 |
| 손 뗀 뒤 0.5 s | 0 m | 0 m |
| 오른쪽 100 px 끌기 | yaw −0.5 rad | −0.5 rad |
| 눈높이 아이 / 어른 | 1.1 / 1.7 m | 1.1 / 1.7 m |
| 두 손가락 벌리기 | 거리 감소 | 12.07 → 2.41 m |
| 고체 물체로 직진 | 반경 0.25 m 앞에서 멈춤 | 벽 앞 0.273 m |
| JS `check()` ↔ Python `check()` | 고정 사례 7개에서 메시지 동일 | 동일 (처음엔 2개 달랐고 테스트가 잡았다) |

legacy:

- `hongdae/F1` aerial·eye 1280×800 렌더 성공 (SwiftShader, CLI). 예제 하나 두 시점 CLI 실행 약 17 s.
- 테스트 8개 통과 (헤드리스 렌더 2개 포함: 640×400 · 샘플 색 200개 초과 · 휘도 표준편차 10 초과 · 아래 띠도 비어 있지 않음, 오류 페이지는 실패로 보고).
- 이 환경에는 matplotlib 이 없어 평면 PNG 는 만들지 않았다 (보고에 "평면 없음" 으로 나온다).

## 라이선스

`vendor/three/` 는 three.js r170 (MIT, `vendor/three/LICENSE`). 출처·범위는 `vendor/three/VENDORED.md`.
