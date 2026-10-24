# 🚀 Local AI Studio & Environment Toolkit

> **온디바이스 하드웨어 정밀 진단부터 LLM 텍스트 추론, 고화질 이미지 생성(SD 1.5 / FLUX.2), 그리고 AnimateDiff 비디오 제작까지 원스톱으로 제공하는 통합 로컬 AI 툴킷**  
> 모던 Qt6 GUI, 마크다운(`.md`) 파일 기반 파이프라인, CLI 자동화 및 6대 OS 사양 진단 도구를 모두 포함하며, 개인정보(로컬 절대 경로 및 사용자 계정명)가 완전히 보호되도록 설계되었습니다.

---

## 🌟 핵심 모듈 개요 (Core Modules)

| 모듈 파일 | 주요 기능 | 입력 방식 | 지원 모델 / 엔진 |
| :--- | :--- | :---: | :--- |
| 🧠 **`llm_runner.py`** | 텍스트 생성 & 연구 분석 | Qt6 GUI / `.md` 파일 / CLI | GGUF 포맷 (Llama 3.1, Qwen 2.5, EXAONE, DeepSeek 등) via `llama.cpp` |
| 🎨 **`stable.py`** | 초고화질 이미지 생성 | Qt6 GUI / `.md` 파일 / CLI | SD 1.5 (`CyberRealistic`) & FLUX.2 [klein] 4B via `Diffusers` |
| 🎬 **`animate_video.py`** | 텍스트-투-비디오 (T2V) | CLI / 파이썬 스크립트 | SD 1.5 + AnimateDiff Motion Module (`.mp4`, `.gif` 출력) |
| 🔍 **`check_env.py`** | 6대 OS 하드웨어 진단 | CLI (자동 마크다운 리포트) | Windows, macOS, Linux, iOS, iPadOS, Android (Zero Dependency) |

---

## 💡 주요 특징 (Key Features)

### 1. 🧠 로컬 LLM 텍스트 생성 스튜디오 (`llm_runner.py`)
- **한국어 & 다국어 완벽 지원**: UTF-8 콘솔 인코딩 대응으로 한글 질문 및 고품질 한글 답변 완전 보장.
- **연구/시뮬레이션 특화 (무검열 환경)**: 거부 반응(Refusal) 없는 객관적 전술/군사/특수 주제 분석 가능.
- **3대 사용자 인터페이스**:
  - **🖥️ Qt6 모던 GUI (`--gui`)**: 사용 가능한 GGUF 모델 자동 인식, 실시간 토큰 스트리밍, 결과 파일 원클릭 저장.
  - **📄 마크다운 파일 I/O (`-f`)**: 질문을 `.md` 파일로 입력받아 답변도 `.md` 문서로 자동 생성 및 저장.
  - **⚡ CLI 커맨드라인**: 스크립트 연동 및 단일 쿼리 즉시 실행.
- **하드웨어 가속**: RTX 3060 (12GB VRAM) 환경에서 `-ngl 99`로 전량 GPU 오프로드하여 쾌속 추론.

### 2. 🎨 차세대 이미지 생성 스튜디오 (`stable.py`)
- **듀얼 아키텍처 지원**: 고품질 실사 인물 특화 **SD 1.5** 및 초고속 4스텝 **FLUX.2 [klein] 4B** 탑재.
- **메모리 최적화 (12GB VRAM & 32GB RAM)**:
  - `Model CPU Offload` 및 `PyTorch SDPA` 적용으로 VRAM 3GB 수준의 안정적인 구동.
  - `VAE Tiling & Slicing` 지원으로 1536×1536 이상의 초고해상도에서도 OOM(메모리 부족) 방지.
- **사용자 편의 기능**: Qt6 GUI 내 이미지 실시간 미리보기 및 결과 저장 폴더 원클릭 열기 지원.

### 3. 🎬 텍스트-투-비디오 (Text-to-Video) 엔진 (`animate_video.py`)
- **AnimateDiff 모션 모듈 결합**: 로컬 SD 1.5 실사 체크포인트와 결합하여 연속 모션 프레임 생성.
- **가벼운 VRAM 점유**: `Attention Slicing` 및 `Model CPU Offload`로 12GB VRAM 중 **단 3.5GB만 점유**하며 안정적 구동.
- **다양한 포맷 출력**: `.mp4` 동영상 및 애니메이션 `.gif` 포맷 지원.

### 4. 🔍 크로스 플랫폼 사양 진단 도구 (`check_env.py`)
- **6대 OS 지원**: `Windows`, `macOS`, `Linux`, `iOS`, `iPadOS`, `Android`.
- **제로 의존성 (Zero Dependency)**: 외부 라이브러리 없이 Python 표준 라이브러리만으로 하드웨어 정밀 감지.
- **AI 모델 추천 매트릭스**: 현재 기기 스펙에 맞는 최적의 LLM 파라미터(1B~70B) 및 권장 실행 엔진(Ollama, vLLM, Draw Things 등) 안내.
- **보고서 자동 생성**: 콘솔 출력과 동시에 마크다운(`ai_env_report.md`) 리포트 자동 저장.

---

## 📂 프로젝트 구조

```text
├── models/                     # 로컬 모델 체크포인트 (.safetensors, .gguf)
│   ├── CyberRealistic_FINAL_FP16.safetensors
│   └── flux-2-klein-4b.safetensors
├── outputs/                    # 생성된 이미지/비디오/분석 리포트 저장 폴더
│   ├── marathon_winner.png     # 생성된 고화질 이미지
│   ├── marathon_finish.mp4     # 생성된 비디오 클립
│   └── urban_warfare_analysis.md # 생성된 LLM 분석 마크다운 보고서
├── llm_runner.py               # 로컬 LLM 추론 엔진 (Qt6 GUI / CLI / Markdown I/O)
├── stable.py                   # 통합 이미지 생성 엔진 (Qt6 GUI / CLI / Markdown)
├── animate_video.py            # AnimateDiff 기반 텍스트-비디오 생성 엔진
├── check_env.py                # 6대 OS 환경 진단 및 모델 추천 스크립트
├── prompt_sample.md            # 이미지 생성용 마크다운 샘플
├── llm_prompt_sample.md        # LLM 텍스트 생성용 마크다운 샘플
└── README.md                   # 프로젝트 전체 안내 문서
```

---

## 🛠️ 설치 및 요구사항 (Prerequisites)

- **OS**: Windows, macOS, Linux
- **Python**: 3.10 이상 권장
- **GPU**: NVIDIA CUDA 지원 GPU (RTX 3060 12GB 최적화)

```bash
# PyTorch (CUDA 12.4 권장)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# 핵심 패키지 및 Qt6 GUI, 비디오 도구 설치
pip install diffusers transformers accelerate safetensors PySide6 imageio imageio-ffmpeg
```

> **참고**: `llm_runner.py`는 고속 추론을 위해 `llama.cpp` 바이너리(예: `C:\llama.cpp\llama-cli.exe` 또는 시스템 PATH)와 연동됩니다.

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 1. 🧠 로컬 LLM 텍스트 생성 (`llm_runner.py`)

#### ① 모던 Qt6 GUI 실행 (추천)
```bash
python llm_runner.py --gui
```
- 드롭다운으로 로컬 GGUF 모델을 선택하고, 실시간 스트리밍 답변을 확인한 뒤 원클릭으로 `.md` 파일 저장이 가능합니다.

#### ② 마크다운(`.md`) 파일 입력 ➡️ 마크다운 파일 출력
```bash
python llm_runner.py -f llm_prompt_sample.md
```
- 질문 마크다운 문서를 읽어 분석을 수행하고, 결과 마크다운 문서(`outputs/..._analysis.md`)를 자동 생성합니다.

#### ③ CLI 단일 질문 (한글 지원)
```bash
python llm_runner.py -p "현대 도심지 시가전의 핵심 전술적 과제 3가지를 분석해 줘." -n 350
```

---

### 2. 🎨 이미지 생성 스튜디오 (`stable.py`)

#### ① 모던 Qt6 GUI 실행
```bash
python stable.py --gui
```
- 긍정/부정 프롬프트, 해상도, 스텝, 시드를 직관적으로 설정하고 생성된 이미지를 미리보기합니다.

#### ② 마크다운 파일 기반 실행
```bash
python stable.py -f prompt_sample.md
```

#### ③ 초고해상도 (1536x1536) FLUX.2 Klein 실행
```bash
python stable.py --model models/flux-2-klein-4b.safetensors --width 1536 --height 1536 --steps 4 --scale 1.0 --output outputs/flux_highres.png
```

---

### 3. 🎬 AnimateDiff 비디오 생성 (`animate_video.py`)

```bash
# 기본 실행 (마라톤 결승 통과 16프레임 동영상 생성)
python animate_video.py

# 커스텀 프롬프트 및 비디오 옵션 지정
python animate_video.py \
  --prompt "cinematic slow motion of an athletic runner crossing the finish line in first place, 8k" \
  --frames 16 \
  --fps 8 \
  --output outputs/marathon_finish.mp4

# 애니메이션 GIF로 저장
python animate_video.py --output outputs/animation.gif
```

---

### 4. 🔍 컴퓨터 환경 정밀 진단 (`check_env.py`)

```bash
# 기본 진단 (화면 출력 + ai_env_report.md 자동 저장)
python check_env.py

# 텍스트(.txt) 리포트로 저장
python check_env.py -o ai_env_report.txt

# 파일 저장 없이 화면에만 보기
python check_env.py --no-save
```

---

## 🖼️ 실제 생성 결과물 샘플 (Deliverables)

| 종류 | 장면 및 내용 | 세부 사양 | 파일 위치 |
| :---: | :--- | :--- | :---: |
| **텍스트/보고서** | **현대 도심지 시가전 전술 분석** | `Meta-Llama-3.1-8B Q4` / GPU 99 레이어 / 한국어 답변 | `outputs/urban_warfare_analysis.md` |
| **이미지** | **1위로 결승선을 통과하는 마라토너** | `CyberRealistic FP16` / `768x512` / 28스텝 (약 7초 소요) | `outputs/marathon_winner.png` |
| **비디오** | **마라톤 결승 통과 모션 클립** | `AnimateDiff v1.5-2` / `512x512` / 16프레임 / 8fps (VRAM 3.5GB) | `outputs/marathon_finish.mp4` |

---

## 💡 자주 묻는 질문 및 트러블슈팅 (FAQ & Tips)

- **Q: `llm_runner.py` 실행 시 한글을 입력해도 되나요?**
  - **A**: 네, 완벽히 지원됩니다. Windows 콘솔의 `cp949` 충돌을 방지하는 `UTF-8` 자동 재설정 코드가 내장되어 있어 터미널, GUI, 마크다운 파일 입출력 모두 한글이 깨지지 않고 정상 처리됩니다.
- **Q: 실행 시 `A matching Triton is not available` 경고가 뜹니다.**
  - **A**: Triton은 Linux 전용 라이브러리로 Windows용 빌드가 제공되지 않습니다. 현재 PyTorch 2.0+ 내장 C++ 하드웨어 가속 엔진(SDPA)이 정상 가동 중이므로 **별도 설치가 필요 없으며 성능 저하도 없습니다.**
- **Q: 고해상도 이미지/비디오 생성 시 VRAM이 부족(OOM)하지 않나요?**
  - **A**: 모든 스크립트에 `Model CPU Offload`와 `Attention/VAE Slicing` 최적화가 기본 적용되어 있어, 12GB VRAM 환경에서도 1536x1536 고해상도 이미지와 비디오를 안전하게 생성합니다.
- **Q: GitHub에 등록할 때 개인 경로나 사용자명이 노출되지 않나요?**
  - **A**: 모든 코드는 하드코딩된 개인 절대 경로(`C:\Users\...`)를 완전히 제거하고, `shutil.which` 및 `os.path.expanduser("~")` 기반의 동적 탐색 로직을 채택하여 개인정보를 철저히 보호합니다.

---

## 📜 라이선스 (License)

이 프로젝트는 [MIT License](LICENSE)에 따라 자유롭게 사용, 연구 및 배포할 수 있습니다.
