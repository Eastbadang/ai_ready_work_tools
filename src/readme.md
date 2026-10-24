# 🚀 Local AI Studio & Environment Checker

> **온디바이스 AI 환경 진단부터 최신 Stable Diffusion & FLUX.2 이미지 생성, 그리고 AnimateDiff 비디오 생성까지 원스톱으로 지원하는 로컬 AI 툴킷**  
> 모던 Qt6 GUI, 마크다운 파일 기반 입력, CLI 모드, 동영상 생성 엔진 및 6대 OS 사양 진단 도구를 제공합니다.

---

## 🌟 주요 특징 (Key Features)

### 1. 🎨 고품질 이미지 생성 스튜디오 (`stable.py`)
- **듀얼 아키텍처 지원**: 고품질 실사 인물 특화 **SD 1.5** (`CyberRealistic`) 및 초고속 4스텝 **FLUX.2 [klein] 4B** 지원
- **3대 인터페이스 제공**:
  - **🖥️ Qt6 모던 GUI (`PySide6`)**: 직관적인 컨트롤, 비동기 백그라운드 추론, 실시간 미리보기, 저장 폴더 원클릭 열기
  - **📄 마크다운/텍스트 파일 입력 (`-f`)**: 프롬프트와 옵션을 `.md` / `.txt` 문서로 깔끔하게 관리
  - **⚡ CLI 커맨드라인**: 스크립트 자동화 및 파이프라인 연동 지원
- **RTX 3060 12GB 메모리 최적화**:
  - `Model CPU Offload` 및 `PyTorch SDPA` 적용으로 VRAM 3GB대의 쾌적한 구동
  - `VAE Tiling & Slicing` 지원으로 1536×1536 이상의 초고해상도에서도 OOM(메모리 부족) 방지

### 2. 🎬 텍스트-투-비디오 (Text-to-Video) 엔진 (`animate_video.py`)
- **AnimateDiff 모션 모듈 결합**: 로컬 SD 1.5 체크포인트와 결합하여 연속 모션 프레임 렌더링
- **로컬 무검열 연구/시뮬레이션 환경**: 클라우드 API와 달리 자체 Safety Checker를 해제하여 연구 목적의 역동적인 장면(전장 시뮬레이션, 스포츠 액션 등)을 자유롭게 생성
- **가벼운 VRAM 점유**: `Attention Slicing` 및 `Model CPU Offload`로 12GB VRAM 중 **단 3.5GB만 점유**하며 안정적 구동
- **다양한 포맷 출력**: `.mp4` 동영상 및 애니메이션 `.gif` 형식 지원

### 3. 🔍 크로스 플랫폼 사양 진단 도구 (`check_env.py`)
- **6대 OS 지원**: `Windows`, `macOS`, `Linux`, `iOS`, `iPadOS`, `Android`
- **제로 의존성 (Zero Dependency)**: 외부 라이브러리 없이 Python 표준 라이브러리만으로 하드웨어 정밀 감지
- **AI 모델 추천 매트릭스**: 현재 기기 스펙에 맞는 최적의 LLM 파라미터(1B~70B) 및 권장 실행 엔진(Ollama, vLLM, Draw Things 등) 안내
- **보고서 자동 생성**: 콘솔 출력과 동시에 마크다운(`ai_env_report.md`) 리포트 자동 저장

---

## 📂 프로젝트 구조

```text
├── models/                     # 로컬 모델 가중치 (.safetensors)
│   ├── CyberRealistic_FINAL_FP16.safetensors
│   └── flux-2-klein-4b.safetensors
├── outputs/                    # 생성된 이미지 및 동영상 저장 폴더
│   ├── marathon_winner.png     # 생성된 고화질 이미지
│   └── marathon_finish.mp4     # 생성된 비디오 클립
├── stable.py                   # 통합 이미지 생성 엔진 (Qt6 GUI / CLI / File)
├── animate_video.py            # AnimateDiff 기반 텍스트-비디오 생성 엔진
├── check_env.py                # 6대 OS 환경 진단 및 모델 추천 스크립트
├── prompt_sample.md            # 파일 기반 실행용 마크다운 샘플
└── README.md                   # 프로젝트 전체 안내 문서
```

---

## 🛠️ 설치 및 요구사항 (Prerequisites)

- Python 3.10 이상 권장
- NVIDIA GPU (CUDA 지원 권장, RTX 3060 12GB 최적화)

```bash
# PyTorch (CUDA 12.4 권장)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# 핵심 라이브러리 및 GUI, 비디오 도구 설치
pip install diffusers transformers accelerate safetensors PySide6 imageio imageio-ffmpeg
```

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 1. 이미지 생성 스튜디오 (Qt6 GUI)
```bash
python stable.py --gui
```
- 화면에서 긍정/부정 프롬프트, 해상도, 스텝, 시드를 마우스로 편리하게 조작할 수 있습니다.
- `[📂 프롬프트/설정 파일 불러오기]` 버튼으로 `.md` 파일을 원클릭 로드할 수 있습니다.
- 생성이 완료되면 우측 화면에 이미지가 렌더링되며, `[📁 저장 폴더 열기]` 버튼으로 결과물을 바로 확인할 수 있습니다.

---

### 2. 마크다운(`.md`) 파일 기반 이미지 생성
```bash
python stable.py -f prompt_sample.md
```

**`prompt_sample.md` 구성 예시:**
```markdown
# Prompt
(masterpiece, best quality, ultra-detailed, photorealistic:1.35), dynamic action shot of an athletic marathon runner crossing the finish line in first place, breaking the red finish line tape with chest, arms raised in victory, emotional triumphant expression, athletic running wear, cheering crowd, city street marathon, confetti, morning sunlight, 8k, professional sports photography

# Negative Prompt
(worst quality, low quality:1.4), (deformed, bad anatomy, unnatural pose, twisted body, malformed limbs, disconnected limbs, bad proportions:1.4), (mutated hands and fingers:1.3), blurry, cartoon, illustration, watermark, text

# Settings
- model: models/CyberRealistic_FINAL_FP16.safetensors
- width: 768
- height: 512
- steps: 28
- scale: 7.0
- seed: 888
- output: outputs/marathon_winner.png
```

---

### 3. AnimateDiff 텍스트-투-비디오 생성 (`animate_video.py`)
```bash
# 기본 실행 (마라톤 결승 통과 16프레임 동영상 생성)
python animate_video.py

# 커스텀 프롬프트 및 비디오 옵션 지정
python animate_video.py \
  --prompt "cinematic slow motion of a futuristic racing car speeding on a neon highway, motion blur, 8k" \
  --frames 16 \
  --fps 8 \
  --output outputs/racing_car.mp4

# 움직이는 GIF 형식으로 저장
python animate_video.py --output outputs/animation.gif
```

---

### 4. 컴퓨터 환경 진단 및 맞춤 AI 모델 추천 (`check_env.py`)
```bash
# 기본 진단 (콘솔 출력 + ai_env_report.md 자동 저장)
python check_env.py

# 텍스트(.txt) 리포트로 저장
python check_env.py -o ai_env_report.txt
```

---

## 🖼️ 실제 결과물 샘플 (Deliverables)

| 종류 | 장면 설명 | 세부 사양 | 파일 위치 |
| :---: | :--- | :--- | :---: |
| **이미지** | **1위로 결승선을 통과하는 마라토너** | `CyberRealistic FP16` / `768x512` / 28스텝 (약 7초 소요) | `outputs/marathon_winner.png` |
| **비디오** | **마라톤 결승 통과 애니메이션** | `AnimateDiff v1.5-2` / `512x512` / 16프레임 / 8fps (VRAM 3.5GB) | `outputs/marathon_finish.mp4` |

---

## 💡 자주 묻는 질문 및 트러블슈팅 (FAQ & Tips)

- **Q: 실행할 때 `A matching Triton is not available` 경고가 뜹니다.**
  - **A**: Triton은 Linux 전용 라이브러리로 Windows용 공식 빌드가 제공되지 않습니다. 현재 PyTorch 2.0+ 내장 C++ 하드웨어 가속 엔진(SDPA)이 정상 가동 중이므로 **별도 설치가 필요 없으며 성능 저하도 없습니다.**
- **Q: 고해상도 생성 시 VRAM이 부족(OOM)하지 않나요?**
  - **A**: `stable.py`와 `animate_video.py`에 `Model CPU Offload`와 `Attention/VAE Slicing`이 기본 내장되어 있어, 12GB VRAM 환경에서도 1536x1536 고해상도 이미지와 16프레임 비디오를 쾌적하게 생성할 수 있습니다.

---

## 📜 라이선스 (License)

이 프로젝트는 [MIT License](LICENSE)에 따라 자유롭게 사용, 연구 및 배포할 수 있습니다.
