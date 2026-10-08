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

`robot` 플러그인: `robot.arm` — URDF 사슬(JSON)과 관절 궤적을 재생하고, 펜이 내려간 곳에 잉크를 남긴다. 잉크 위치는 런타임 자신의 FK(`runtime/src/robot/kinematics.js`)로 계산한다.

## 그림 그리는 로봇 (SPEC 6절 2단계 · V-16)

```bash
python3 -m worldengine draw                       # 데모(별·원·나선) → 계획 · V-16 보고 · 세계 · 렌더(그리는 중/끝)
python3 -m worldengine draw --svg my.svg --scale 0.002   # M/L/H/V/Z 경로만. 곡선은 거부한다(조용히 펴지 않는다)
```

| 단계 | 어디 | 무엇 |
|---|---|---|
| 몸 | `kinematics/*.urdf` → `robot.load_chain` | 기준 구현(`kinematics/`, main 에 병합됨)의 URDF 파서를 그대로 쓴다 |
| 역기구학 | `draw.ik` | 감쇠 최소제곱(DLS) + 휴식 자세 쪽 영공간 당김. 직전 자세에서 시작하므로 표본 사이 가지 뒤집힘이 없다 (기준 평면 IK는 점마다 첫 가지를 돌려준다) |
| 궤적 | `draw.plan` | 획 재표본(2 cm) · 펜 들기는 도구 동작 · 시간 = 손끝 속도와 관절 속도 한계 중 느린 쪽 |
| 검증 | `draw.verify` | 기준 FK 로 획 오차 · 표본 사이 관절 보간 중점 오차 · 도달 실패 · 기준 `check_trajectory` 한계 위반 · 이웃 아닌 링크 간격(자기 충돌) · 관절 속도 |
| 재생 | `robot.arm` | JS FK 가 기준 test_vectors 600개와 1e-9 m 이내로 일치 (node 테스트) · 브라우저 안에서 잉크 ↔ 의도한 획 비교 (self-test) |

데모 측정 (개념 카드 없이, planar_3_dof, 표본 862, 재생 54.7 s): 획 오차 최대 0.010 mm · 보간 중점 0.039 mm · 도달 실패 0 · 한계 위반 0 · 자기 충돌 0 (최소 링크 간격 0.99 m) · 관절 속도 최대 0.58 rad/s (한계 1.5, 기본값 — URDF velocity 는 기준 파서가 읽지 않는다). 브라우저 잉크 ↔ 의도한 획 최대 0.010 mm. 저장소의 `worlds/drawing_robot.world.json` 은 개념 카드를 적용한 판이다 (아래).
일부러 한계를 넘는 그림(joint1 을 [−1.2, −0.9] rad 로 좁힘): 한계를 지키며 계획하면 도달 실패로, 한계를 무시하고 계획하면 기준 검사기가 위반 134건으로 잡는다 — 둘 다 FAIL. 6축 팔(arm_6_dof)도 같은 계획기로 사각형을 그려 통과.

### 개념 카드 (다섯 재료 중 개념)

세계의 `concepts` 에 카드를 단다: `id · title · statement · sources[{who, kind: quote|paraphrase|own|interview, where, note}] · rules[{param, value, why}] · drives[엔티티 id]`.
출처 없는 개념, 출처(where) 없는 인용, 없는 엔티티를 가리키는 drives 는 JS·Python 검사가 같은 문장으로 거부한다.
규칙은 `worldengine/concept.py` 가 계획기 설정으로 바꾸고(지원: `pen.lifts`=0, `draw.v_draw`, `draw.max_strokes`), **끝난 궤적에서 다시 측정해** 지켰는지 적는다. 모르는 규칙은 "적용 안 됨 + 이유"로 남는다.

데모 카드 "산책하는 선" — Paul Klee 의 널리 퍼진 의역(원문 인용 아님, 그렇게 표시)을 데모가 규칙 둘로 번역: 펜을 떼지 않는다, 0.15 m/s 로 천천히.
측정: 개념 없음 → 그리는 도중 펜 떼기 2회 · 54.7 s / 개념 적용 → 0회 · 97.0 s · 최대 펜 속도 0.15 m/s, 두 경우 모두 V-16 통과 (획 오차 0.0099 mm).
링크에 `&card=1` 을 붙이면 카드를 연 채로 시작한다.

좌표: 미터, z 위, x 동, y 북. three.js 의 y-위로 바꾸는 곳은 `engine.js` 의 root 그룹 한 곳뿐.

## 출처

파일별 원본 blob 해시와 변경 여부는 [`PROVENANCE.md`](PROVENANCE.md) (테스트가 해시를 다시 계산해 확인한다).

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
#   …/runtime/index.html?world=../worlds/drawing_robot.world.json   ← 로봇이 그림을 그린다
python3 -m unittest discover -s tests -v   # node 가 있으면 runtime/tests/*.test.mjs 도 함께 돈다
```

보고의 `백엔드:` 줄이 각 그림을 실제로 무엇이 그렸는지 말한다: `three.js r170 · headless chromium (CLI|playwright)` / `matplotlib 대체(비실사)` / `없음`.

## 1단계 핵심: 다섯 재료 · 플러그인 규약 · 적합성 키트 · 기준 세계 3개

| 재료 | world/1 필드 | 검사 |
|---|---|---|
| 개념 | `concepts` (출처·종류·규칙·drives) | JS·Python 같은 문장 |
| 세계 | `rules.axes` (밀도·색·형태·질감·움직임·소리·서사 [0,1], 확장 가능) · `rules.constraints` (`dimension_series` · `palette` · `max_elements`) | 같은 검사 + `worldengine/constraints.py` 가 몸(엔티티)에 적용 |
| 몸 | `entities` | 플러그인 유형 |
| 행동 | 엔티티의 `behaviors`, 로봇 궤적 | |
| 표현 | `expressions` (`web3d`, 생성기 플러그인) | |

`version`, `forked_from` 로 판과 갈래를 남긴다. 레시피는 세계의 해시를 담아, 다른 판의 세계로 재생하려 하면 거부한다.

**생성기 플러그인** (`engine/plugins/<이름>/plugin.py`, 규약은 `worldengine/plugins.py`): `translate(축) → 매체 파라미터` (G-02, 고칠 수 있다) · `generate(세계, 의도, 파라미터) → 결과물` (+ 핵심이 붙이는 레시피, G-01) · `self_assess` (G-03) · `ports` (팔레트·템포·이벤트, G-04).
첫 플러그인 둘: `image_svg` (절차적 2D, M-01) · `plotter` (그림 그리는 로봇을 생성기로 — 잉크는 기준 FK 로 계산한 펜 끝).

**적합성 키트** (`python3 -m worldengine conform`, G-05): 플러그인마다 기준 세계마다 G-01 · V-05(레시피로 다시 만들면 바이트 동일) · G-02(파라미터 하나를 고치면 결과가 바뀜 — 결과가 반복될 때만 판정) · G-03 · G-04.
측정: 플러그인 2 × 세계 3 × 조항 5 = 30/30 통과. 일부러 망가뜨린 플러그인(호출마다 결과가 다름)은 V-05·G-02 에서 떨어진다.

**V-02 (핵심 수정 0줄)**: `tests/test_stage1.py` 가 핵심 파일(`worldengine/**/*.py`, `runtime/src/**/*.js`, `runtime/index.html`) 전부의 sha256 을 잰 뒤, 저장소 밖 임시 폴더에 새 플러그인을 써서 발견·적합성 시험·모든 플러그인 실행을 하고, 다시 잰다 — 같아야 통과.

**기준 세계 3개** (`worlds/ref_*.world.json`, 인터뷰 작가와 무관하게 일부러 극단으로, 7.1절):
- A 여백 — 엔티티 3개, 색 2개 (`max_elements` 7, `palette`)
- B 축제 바로크 — 엔티티 52개, 8색, 돌고 떠다니는 것 31개
- C 모듈러 거리 — 모든 치수가 Le Corbusier, *Le Modulor* (1950) 의 붉은·푸른 계열 값 (cm 반올림값을 미터로; 의역 표시, 글·그림은 옮기지 않음). 계열 밖 치수를 하나 심으면 `constraints.py` 가 잡는다

셋 다 핵심 유형만 쓰고 수정 없는 런타임으로 렌더된다 (V-01).

**V-04 첫 측정 (목표 미정 — SPEC: 측정 후 목표 설정).** 측정기 `worldengine/measure.py` 는 결과물 SVG 만 읽고 플러그인을 부르지 않는다. 방법(밀도·색·형태·질감·움직임을 SVG 에서 계산하는 식)은 숫자를 보기 전에 그 파일 머리말에 고정했다. 각 결과물의 측정 축과 세 세계 축 사이 거리(공통 축 RMS)를 재서 자기 세계가 몇 번째로 가까운지 본다.

| 플러그인 | 세계 | 밀도·색·형태·질감·움직임 (측정) | 가장 가까운 세계 | 자기 세계 순위 |
|---|---|---|---|---|
| image_svg | 여백 | 0.27 · 0.00 · 0.50 · 0.02 · 0.06 | 여백 | 1 |
| image_svg | 축제 바로크 | 0.98 · 0.91 · 0.88 · 0.49 · 0.96 | 축제 바로크 | 1 |
| image_svg | 모듈러 | 0.77 · 0.37 · 0.11 · 0.25 · 0.23 | 모듈러 | 1 |
| plotter | 여백 | 0.38 · 0.00 · 0.24 · 0.00 · 0.00 | 여백 | 1 |
| plotter | 축제 바로크 | 0.70 · 0.50 · 0.53 · 0.00 · 0.00 | 모듈러 | **3** |
| plotter | 모듈러 | 0.61 · 0.00 · 0.00 · 0.00 · 0.00 | 모듈러 | 1 |

6개 중 5개가 자기 세계에 가장 가깝다. plotter 의 바로크는 꼴찌 — 펜 하나·색 하나·회전 없음이라 색·질감·움직임 축을 실을 수 없다. 측정기를 고쳐 맞추지 않았다; 매체의 한계로 기록한다 (펜 여러 자루·색 바꾸기는 다음 과제).

## 3단계: 대화형 스튜디오 (A-01~A-07) · 시안 보드 (D) · V-13 시험틀

```bash
pip install -r requirements-studio.txt                  # 에이전트를 쓸 때만 (공식 anthropic SDK)
export ANTHROPIC_API_KEY=...                            # 서버 프로세스에만 둔다 — 브라우저로 가지 않는다
python3 -m worldengine studio --world worlds/ref_yeobaek.world.json --artist 작가이름 [--host 0.0.0.0]
```
출력된 주소(무작위 토큰 포함)를 PC나 휴대폰 브라우저로 연다. 키가 없으면 에이전트 없이 열리고 그렇다고 말한다.

| 요구 | 어떻게 |
|---|---|
| A-01 한국어 + 이미지 | 채팅 + 사진 첨부(긴 변 1568 px 로 줄여 보냄) → Messages API 이미지 블록 |
| A-02 해석을 숨기지 않음 | 에이전트 도구는 **제안만** 한다 (`propose_*`). 카드에 "이렇게 이해했어요" 변경 목록 + 이유, 축은 슬라이더로 고쳐서 적용. 적용 도구는 에이전트에게 없다 |
| A-03 모호하면 시안 | `propose_variants` 2~3개 → 시안 비교 보드 (D-01~D-04: 해석·변경 요약·축 표·미리보기 측정·3D 시점·레시피) |
| A-04 작가별 어휘 | 작가가 슬라이더로 고쳐 적용하면 "한 말 → 우리가 이해한 값 → 고친 값"을 `~/.worldengine/studio/vocab/<작가>.json` 에 기록 (저장소 밖, gitignore 도 걸어 둠). 서버가 모델의 시스템 프롬프트에만 넣는다 |
| A-05 판과 되돌리기 | 적용마다 새 판. "아까가 나았어" → `propose_revert` (되돌리기도 새 판, 기록은 안 지워짐) |
| A-06 승인 | 고해상도 렌더·작품 삭제·외부 공개·실제 장치는 `request_action` 으로 대기열에만. 작가가 승인 버튼을 눌러야 실행. 장치 구동기는 아직 없다고 답한다. 공개는 폴더만 만들고 배포하지 않는다 |
| A-07 못 하는 것 | `cannot_do` 로 이유와 대안. 바꿔치기 금지는 V-13 채점에도 들어 있다 |

모델 id 는 `worldengine/studio/config.py` 한 곳 (`WE_MODEL` 로 바꿈, 기본 claude-opus-5-5). 도구는 전부 `strict: true`, 사고는 adaptive. 이 모델은 강제 `tool_choice` 를 받지 않아 프롬프트로 도구 사용을 이끈다.
테스트는 대본을 따르는 가짜 클라이언트만 쓰고, 바깥으로 나가는 소켓 연결을 막은 채 돈다. 키·어휘가 서버 응답(페이지·상태·세계·런타임 파일)에 실리지 않는지, 토큰 없이 API 가 막히는지, 경로 우회가 404 인지, 저장소에 키 모양 문자열이 없는지, 워크플로에 키가 없는지 검사한다.

**V-13 시험틀** (`worldengine/studio/v13.py`, `eval/v13_seed.json`): 요청 문장 + 기대 변경 범위(축 방향·건드리면 안 되는 축·추가할 몸·출처 종류·시안·승인·거절·되돌리기) 24쌍. **개발자가 쓴 시드 세트이고 작가의 말이 아니다** — 인터뷰 8번 질문의 답으로 바꾼다. 채점기는 가짜 클라이언트로 시험했다 (범위 안·방향 틀림·다른 축 침범·바꿔치기).
**V-13 숫자는 아직 없다.** 실제 모델로 돌리려면 키와 비용이 든다: `python3 -m worldengine v13` 이 먼저 상한(요청 수·출력 토큰)을 보여 주고, `--yes` 를 붙여야 실행한다.

## 4단계: 경험 런타임 확장 (XR-03·04·05·07·11) · 말하는 캐릭터 (CH-01~04) · V-18

데모 `worlds/talking_garden.world.json` (말하는 정원 — 작가 작품 아님).

| 요구 | 어떻게 |
|---|---|
| XR-03 세계 규칙 → 물리 | `rules.physics {gravity_mps2, time_scale}`. 세계 시계는 time_scale 로 흐르고(행동·로봇이 읽음), 관객의 이동·자막·시선·투어는 실제 시간. `fall` 행동은 중력으로 떨어지고 튄다 (해석식이라 어느 시각을 바로 렌더해도 같다) |
| XR-04 공간 음향 | `sound` 엔티티 — 오디오 파일 없이 tone/chord/noise/pulse, Web Audio PannerNode(HRTF, 거리 감쇠), 듣는 위치는 카메라. **관객이 한 번 누르기 전에는 AudioContext 를 만들지 않는다** |
| XR-05 상호작용 | 엔티티 `triggers`: `tap`(10 px·600 ms 안의 누름 — 궤도 끌기·조이스틱과 구별) / `near`(반경) → play · toggle · caption · tour · talk |
| XR-11 안내·자막·투어 | 첫 방문 안내 한 장(그 '시작' 버튼이 소리를 켜는 몸짓), **소리·대사·투어 정지점마다 자막이 없으면 세계 검사가 거부**, 작가가 정한 카메라 투어(`tours`) |
| XR-07 저사양 | `?lowspec=1`, 또는 처음 60프레임이 30 fps 미만이면 자동: 화소비 1, 그림자·환경 반사 끔, 점광원 4개까지 |
| CH-01 성격 | `character` 엔티티의 이름·대사·persona + 세계의 개념 카드·서사 축으로 시스템 프롬프트를 만든다 (코드에 성격 없음) |
| CH-02 몸짓·시선 | 머리가 관객(카메라) 쪽으로 돌고, 말하는 동안 팔이 움직인다 |
| CH-04 안전 | 입력 300자, 메일·전화·주민번호 꼴은 `[개인정보]` 로 바꾼 뒤에만 모델로 보냄, 금칙어(`worldengine/safety/blocklist.txt`, 공개 전 사람이 검토)면 모델을 부르지 않고 캐릭터 말투의 거절, 출력 400자·금칙어면 거절로 대체, 기억은 방문마다 최근 6턴·RAM·10분 — **디스크에 아무것도 쓰지 않고 요청 로그도 없다**, 주소별 요청 제한, 4 KB 요청 상한 |

정적 사이트에서는 캐릭터가 대본 대사를 말한다. 실시간 대답은 `python3 -m worldengine exhibit --world worlds/talking_garden.world.json` (서버에 키가 있을 때만; 키는 서버 밖으로 나가지 않는다).

**V-18 시나리오** — 구동기를 분명히 적는다: Python 이 headless Chromium(경량 셸 또는 일반 Chromium)을 띄우고, 페이지의 `scenario` 자체 시험이 캔버스·조이스틱에 PointerEvent 를 보내 **런타임 자신의 이벤트 처리기**가 받는다. Playwright 가 아니다 (이 환경에 설치할 수 없다). 단계: 입장 → 조이스틱으로 걸어 문의 근접 트리거 (2.13 s 걸음) → 달을 눌러 소리+자막 → 산책자를 눌러 대사 자막 → 투어 끝까지(정지점 자막 3개). CI 에서 돈다.

**V-17 (성능)과 CH-03 (모델 응답 지연)은 여기서 숫자를 내지 않는다.** V-17 은 실제 기기에서 `?perf=1` 오버레이(FPS·최악 프레임·첫 로딩·JS 힙)로 잰다. CH-03 은 서버가 자기 몫(모델 호출 제외)만 재고, 모델 지연은 실제 키·네트워크에서 잰다.

## 5단계: 예상 못 한 요구 (N-02~N-05) · 개념 번역기 (CT) · 모순 결합 (K) · V-12/V-14/V-15

| 요구 | 어떻게 |
|---|---|
| N-02 열린 데이터 | 모르는 필드가 검사·스튜디오 제안/적용/되돌리기·사이트 공개·결합을 거쳐도 그대로 남는다 (시험) |
| N-03 샌드박스 | `worldengine/sandbox.py` — `nobody` 사용자로, 새 사용자·네트워크·마운트·PID 네임스페이스(`unshare -rmnpf --kill-child`): 네트워크 장치 없음, 모든 마운트 읽기 전용, 쓰기는 64 MB tmpfs 한 곳, 환경 변수 비움, CPU·메모리·프로세스 수·파일 크기·시간 제한, node 는 `--permission` 추가. **격리를 못 만들면 실행하지 않는다** (`python3 -m worldengine sandbox-probe`) |
| N-04 승격 | 샌드박스 코드 → 적합성 키트(G-05, 샌드박스 안에서) → 작가 승인(A-06) → 작가의 비공개 플러그인 폴더. **승격된 플러그인도 매번 샌드박스에서 돈다** |
| N-05 기록부 | `cannot_do` 마다 경로·종류(고정 범주)·이유·대안을 작가 데이터 폴더에 남긴다. 내보내기는 동의 없으면 경로·범주·대안 수·날짜만 (작가의 말·이유 문장 없음) |
| CT-01~03 | `propose_interpretations`: 개념(출처 포함) → 해석 2~3개, 각각 근거와 실행 규칙(축·움직일 몸·행동) → 시안 보드. 해석은 개념 카드에 남는다 |
| CT-04 | 이름 붙은 작품·화풍을 "그대로/똑같이" 따르려는 요청에 **경고만** (막지 않음, 법적 판단 안 함) |
| K-01~05 | `combine.py`: 몸은 juxtapose·layer·seam·viewpoint(어른 눈높이엔 A, 아이 눈높이엔 B — 런타임 `eye_only`), 축은 per_region·viewpoint·time·per_axis… **평균은 요청할 때만, 기본값이 아니다**. 출처 세계(이름·판·해시)와 결합 방식·대립 쌍을 기록 |
| K-06 / V-09 | 알아볼 수 있는가 — 각 원본 세계의 몸·재질·축 보존 점수 중 **가장 낮은 값** (한 채널이라도 흐려지면 못 알아본다) |

**V-09 첫 측정** (모듈러 × 축제 바로크, 목표 미정):

| 결합 | A 모듈러 | B 바로크 | 판정 |
|---|---|---|---|
| juxtapose (축 per_region) | 1.00 | 1.00 | both kept |
| viewpoint | 1.00 | 1.00 | both kept |
| layer (축 time) | 1.00 | 1.00 | both kept |
| seam | 0.35 | 0.85 | absorbed by B (경계가 A 의 몸 65% 를 잘랐다) |
| juxtapose + 축 keep_a | 1.00 | 0.44 | absorbed by A |
| layer + 축 average | 0.72 | 0.72 | blurred |

처음 만든 지표(세 채널 평균)는 평균 결합을 "both kept"(0.906)로 잘못 판정했다 — 커밋 전에 가장 낮은 채널 기준으로 바꿨다.
viewpoint 결합을 브라우저에서 재면: 어른 눈높이에 A 의 몸 15개만, 아이 눈높이에 B 의 몸 52개만 보인다.

**V-14 안전망** (`tests/test_stage5.py`, 이 환경에서 9개 모두 실행·통과, 건너뛴 것 0): 네트워크 → 연결 불가 · 임시 폴더 밖 쓰기(저장소·/etc·/var/tmp·/dev/shm·홈) → 전부 거부 · 포크 폭탄 → 프로세스 한도에서 멈추고 자식은 함께 사라짐 · 메모리 → 한도 아래에서 MemoryError · CPU·벽시계 시간 → 종료 · API 키 → 샌드박스 환경에 없음 · node 파일 쓰기·자식 프로세스 → ERR_ACCESS_DENIED · 관절 한계를 넘는 로봇 궤적 → `guard.py` 가 막음(한계·속도·NaN·시간 역행) · 잘못된 도구 입력 → 거부, 세계 그대로.
격리를 못 만드는 기계에서는 이 시험들이 **건너뛰기(skipped)로, 이유와 함께** 보고된다 — 통과로 세지 않는다. CI 는 실행/건너뜀 개수를 로그에 따로 찍는다.

**V-12 숨겨 둔 요구 세트**: 저장소에는 봉인 파일의 해시(`eval/v12_sealed.sha256`)만 둔다 — 아직 없다. 파일은 개발 세션이 보지 않은 채 다른 사람이 쓰고 봉인한다. `python3 -m worldengine v12` 는 해시가 없거나 파일이 없으면 "숫자 없음"을 말한다. 있으면 처리 경로 N1~N5 비율, 핵심 코드 변경 수(실행 전후 해시), 바꿔치기 수를 낸다.
**V-15 정직성**: V-13·V-12 보고에 바꿔치기(못 한다고 해야 할 요청에 다른 제안을 한 경우) 수를 센다.

## 링크로 공유 (XR-06)

```bash
python3 -m worldengine site            # → engine/build/site : runtime + three.js + worlds + 목록 페이지(index.html), 1.7 MB
```
모든 경로가 상대 경로라 어떤 정적 호스트에도 올라간다 (서버 코드 없음). 만든 폴더에서 작품마다 실제 방문 URL 로 헤드리스 로드를 해 본다 (`tests/test_site.py` 도 같은 검사).
file:// 로 직접 열면 브라우저가 모듈·fetch 를 막으니 정적 서버(`python3 -m http.server`)나 호스팅이 필요하다.

GitHub Pages: `.github/workflows/pages.yml` 이 main 에서만 배포한다. **꺼져 있다** — 저장소 주인이 Settings → Pages → Source 를 "GitHub Actions" 로 두고, Actions 변수 `PAGES_ENABLED=true` 를 만들어야 돈다. 공개 여부는 사용자가 정한다.

## 헤드리스 렌더 (브라우저 찾는 순서)

1. `WE_CHROMIUM` 환경변수
2. `/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell` — 뷰포트가 `--window-size` 와 정확히 같다
3. `/opt/pw-browsers/chromium-*/chrome-linux/chrome` — `--headless=new` 에서 뷰포트가 창보다 짧아 아래쪽에 빈 띠가 생긴다. 페이지가 실제 뷰포트를 알려 주면(`WE_VIEWPORT`) 모자란 만큼 창을 키워 다시 찍고 요청 크기로 자른다. 이 브라우저는 창 폭이 최소 500 px 이라 더 좁은 요청(휴대폰 390 px)은 결과의 `viewport` 에 실제 폭(500)이 남는다
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
