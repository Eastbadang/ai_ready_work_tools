# 🚀 Local AI Studio & Environment Checker

> **온디바이스 AI 환경 진단부터 최신 Stable Diffusion & FLUX.2 이미지 생성까지 원스톱으로 지원하는 로컬 AI 툴킷**  
> 모던 Qt6 GUI, 마크다운 파일 기반 입력, CLI 모드 및 6대 OS 사양 진단 도구를 제공합니다.

---

## 🌟 주요 특징 (Key Features)

### 1. 🎨 차세대 이미지 생성 스튜디오 (`stable.py`)
- **듀얼 파이프라인 지원**: 고품질 실사 인물 특화 **SD 1.5** (`CyberRealistic`) 및 초고속 4스텝 **FLUX.2 [klein] 4B** 지원
- **3가지 입력 방식**:
  - **🖥️ Qt6 모던 GUI (`PySide6`)**: 직관적인 컨트롤, 비동기 생성, 실시간 결과 미리보기, 저장 폴더 바로 열기
  - **📄 마크다운/텍스트 파일 입력 (`-f`)**: 프롬프트 및 파라미터를 `.md` / `.txt` 파일로 체계적으로 관리
  - **⚡ CLI 커맨드라인 모드**: 배치 작업 및 스크립트 자동화에 최적화
- **하드웨어 최적화 (RTX 3060 12GB + RAM 32GB)**:
  - `Model CPU Offload` 및 `PyTorch SDPA` 적용으로 VRAM 3GB 수준의 안정적인 구동
  - `VAE Tiling & Slicing` 지원으로 1536×1536 이상의 초고해상도에서도 OOM(메모리 부족) 방지

### 2. 🔍 크로스 플랫폼 사양 진단 도구 (`check_env.py`)
- **6대 OS 지원**: `Windows`, `macOS`, `Linux`, `iOS`, `iPadOS`, `Android`
- **제로 의존성 (Zero Dependency)**: 외부 라이브러리 없이 Python 기본 내장 모듈만으로 하드웨어 정밀 감지
- **AI 모델 추천 매트릭스**: 현재 기기 스펙에 맞는 최적의 LLM 파라미터(1B~70B) 및 권장 실행 엔진(Ollama, vLLM 등) 안내
- **보고서 자동 생성**: 콘솔 출력과 동시에 마크다운(`ai_env_report.md`) 리포트 자동 저장

---

## 📂 프로젝트 구조

```text
├── models/                     # 로컬 모델 체크포인트 (.safetensors)
│   ├── CyberRealistic_FINAL_FP16.safetensors
│   └── flux-2-klein-4b.safetensors
├── outputs/                    # 생성된 이미지 저장 디렉터리
│   └── marathon_winner.png
├── stable.py                   # 통합 이미지 생성 엔진 (GUI / CLI / File)
├── check_env.py                # 6대 OS 환경 진단 및 모델 추천 스크립트
├── prompt_sample.md            # 파일 기반 실행용 마크다운 샘플
└── README.md                   # 프로젝트 설명 문서
```

---

## 🛠️ 설치 및 요구사항 (Prerequisites)

- Python 3.10 이상 권장
- NVIDIA GPU (CUDA 지원 권장) 또는 Apple Silicon

```bash
# 필수 패키지 설치
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install diffusers transformers accelerate safetensors PySide6
```

---

## 🚀 사용 방법 (Quick Start)

### 1. Qt6 GUI 그래픽 인터페이스 실행
```bash
python stable.py --gui
```
- 화면에서 긍정/부정 프롬프트, 해상도, 스텝, 시드를 마우스로 편리하게 조작할 수 있습니다.
- `[📂 프롬프트/설정 파일 불러오기]` 버튼을 통해 작성해 둔 `.md` 파일을 원클릭으로 로드할 수 있습니다.
- 생성이 완료되면 우측에 이미지가 미리보기되며, `[📁 저장 폴더 열기]` 버튼으로 바로 확인 가능합니다.

---

### 2. 마크다운(`.md`) 파일 기반 실행
프롬프트와 해상도, 시드 설정을 파일 하나로 관리하여 재현성을 극대화합니다.

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

### 3. CLI 커맨드라인 직접 실행
```bash
# 기본 옵션으로 빠른 실행
python stable.py --prompt "a beautiful cyberpunk city with flying cars, 8k" --output outputs/cyberpunk.png

# 고해상도 (1536x1536) FLUX.2 Klein 실행
python stable.py --model models/flux-2-klein-4b.safetensors --width 1536 --height 1536 --steps 4 --scale 1.0 --output outputs/flux_highres.png
```

---

### 4. 컴퓨터 환경 진단 및 모델 추천
```bash
# 기본 진단 (화면 출력 + ai_env_report.md 자동 저장)
python check_env.py

# 텍스트(.txt) 리포트로 저장
python check_env.py -o ai_env_report.txt
```

---

## 🖼️ 생성 결과 예시 (Sample Deliverable)

| 장면 설명 | 생성 사양 | 결과 이미지 |
| :--- | :--- | :---: |
| **결승선을 1위로 통과하는 마라토너**<br>*(Triumphant Marathon Winner)* | **Model**: `CyberRealistic FP16`<br>**Resolution**: `768x512`<br>**Steps**: `28` / **CFG**: `7.0`<br>**Time**: 약 7초 (RTX 3060) | `outputs/marathon_winner.png` |

---

## 💡 성능 및 환경 팁 (Troubleshooting & Tips)

- **Q: 실행 시 `A matching Triton is not available` 경고가 뜹니다.**
  - **A**: Triton은 Linux 전용 라이브러리로 Windows용 빌드가 제공되지 않습니다. 현재 PyTorch 2.0+ 내장 C++ 가속 엔진(SDPA)이 정상 가동 중이므로 **별도 설치가 필요 없으며 성능 저하도 없습니다.**
- **Q: 고해상도 생성 시 메모리가 부족(OOM)하지 않나요?**
  - **A**: `stable.py`에 `Model CPU Offload`와 `VAE Tiling` 최적화가 기본 내장되어 있어, 12GB VRAM 환경에서도 1536x1536 이상의 고해상도 이미지를 안전하게 생성할 수 있습니다.

---

## 📜 라이선스 (License)

이 프로젝트는 [MIT License](LICENSE)에 따라 자유롭게 사용, 수정 및 배포할 수 있습니다.
