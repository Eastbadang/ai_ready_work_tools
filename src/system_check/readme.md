
# 🔍 AI Environment Checker (`check_env.py`)

> **크로스 플랫폼 AI 모델(LLM & 이미지 생성 모델) 구동 환경 진단 및 맞춤 추천 도구**  
> 외부 라이브러리 설치 없이, 단 한 줄의 명령어로 현재 기기(PC, Mac, 모바일)의 스펙을 분석하고 최적의 온디바이스 AI 모델과 실행 도구를 제안합니다.

---

## 🌟 주요 특징 (Key Features)

- **🌐 6대 운영체제 완벽 지원**: `Windows`, `macOS`, `Linux`, `iOS`, `iPadOS`, `Android`
- **⚡ 제로 의존성 (Zero Dependency)**: `psutil`이나 `torch`가 없어도 Python 표준 라이브러리(`ctypes`, `subprocess`, `/proc`, `sysctl`)만으로 하드웨어를 정밀 감지
- **🎯 맞춤형 AI 모델 추천**:
  - **텍스트 LLM**: 가용 메모리에 따른 최적 모델 파라미터(1B ~ 70B) 및 양자화 레벨(Q4, Q8, FP16) 추천
  - **이미지 생성 (Diffusion / FLUX)**: VRAM에 최적화된 모델(SD 1.5, SDXL, FLUX.2 Klein 등) 및 최적 해상도 안내
  - **로컬 실행 엔진**: OS별 최적 런타임(Ollama, vLLM, LM Studio, MLX, Draw Things, Termux 등) 제안
- **📄 다양한 리포트 출력**: 콘솔 출력과 동시에 깔끔한 마크다운(`ai_env_report.md`) 또는 텍스트(`ai_env_report.txt`) 보고서 자동 저장

---

## 🖥️ 플랫폼별 감지 방식

| OS | 주요 감지 항목 | 추천 실행 엔진 및 도구 |
| :--- | :--- | :--- |
| **Windows** | Win32 API (`ctypes`), NVIDIA CUDA (`nvidia-smi` / `torch`) | Ollama, LM Studio, vLLM (WSL2), ComfyUI, Diffusers |
| **Linux** | 배포판 식별 (`/etc/os-release`), `/proc/meminfo`, NVIDIA/ROCm/Intel XPU | vLLM (고속 서빙), Ollama, TGI, llama.cpp, ComfyUI |
| **macOS** | Apple Silicon M시리즈 Metal(MPS), 통합 메모리(`sysctl`) | Ollama (Metal), LM Studio, MLX/MLX-LM, Draw Things |
| **iOS (iPhone)** | 모바일 Darwin 샌드박스 감지, 메모리 제한 측정 | PocketPal AI, Draw Things, Private LLM |
| **iPadOS (iPad)** | Apple A/M 시리즈 통합 메모리 감지 | Draw Things, Layla, Enchanted |
| **Android** | `/proc/meminfo`, `/proc/cpuinfo` (Snapdragon, Dimensity AP) | Termux (Ollama / llama.cpp), ChatterUI, MLC LLM |

---

## 🚀 빠른 시작 (Quick Start)

### 1. 기본 실행 (진단 + 마크다운 보고서 생성)
```bash
python check_env.py


## 📜 라이선스 (License)
이 스크립트는 오픈소스이며 자유롭게 수정 및 배포가 가능합니다 (MIT License).
