"""
AI 모델(LLM 및 이미지 생성 모델) 선정을 위한 크로스 플랫폼 환경 진단 도구
지원 OS: Windows, macOS, Linux, iOS, iPadOS, Android
"""

import os
import sys
import platform
import subprocess
import json

# Windows cp949 터미널 인코딩 호환 처리
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def detect_os():
    """운영체제 세부 판별 (Windows, macOS, Linux, iOS, iPadOS, Android)"""
    sys_name = platform.system().lower()
    
    # 1. Android 확인 (Termux, Pydroid 등)
    if "android" in sys.platform.lower() or os.path.exists("/system/build.prop") or "ANDROID_ROOT" in os.environ:
        return "Android"
    
    # 2. Apple Darwin 계열 (macOS, iOS, iPadOS)
    if sys_name == "darwin":
        machine = platform.machine().lower()
        # iOS / iPadOS 디바이스 판별 (Pythonista, a-Shell, iSH 등)
        if "iphone" in machine:
            return "iOS"
        if "ipad" in machine:
            return "iPadOS"
        if os.path.exists("/private/var/mobile"):
            # 모바일 샌드박스 내부인 경우
            return "iOS" if "iphone" in platform.platform().lower() else "iPadOS"
        return "macOS"
    
    # 3. Windows
    if sys_name == "windows":
        return "Windows"
    
    # 4. Linux (배포판 정보 파싱)
    if sys_name == "linux":
        distro_name = "Linux"
        if os.path.exists("/etc/os-release"):
            try:
                with open("/etc/os-release", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            distro_name = line.split("=", 1)[1].strip().strip('"')
                            break
            except Exception:
                pass
        return f"Linux ({distro_name})" if distro_name != "Linux" else "Linux"
        
    return sys_name.capitalize()


def get_system_ram_gb():
    """시스템 RAM(GB) 측정 (OS별 API 및 /proc/meminfo 활용)"""
    # psutil이 설치되어 있는 경우 가장 먼저 확인
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except ImportError:
        pass

    target_os = detect_os()

    # 1. Windows: ctypes Windows API (GlobalMemoryStatusEx)
    if "Windows" in target_os:
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
        except Exception:
            pass

    # 2. macOS / iOS / iPadOS: sysctl hw.memsize
    if any(k in target_os for k in ["macOS", "iOS", "iPadOS"]):
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip()
            return round(int(out) / (1024 ** 3), 1)
        except Exception:
            pass

    # 3. Linux / Android: /proc/meminfo
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 ** 2), 1)
        except Exception:
            pass

    return None


def get_gpu_info():
    """GPU / NPU 및 가용 VRAM 측정 (NVIDIA CUDA, Apple Metal MPS, AMD ROCm, Intel XPU 등)"""
    gpu_list = []
    
    # 1. PyTorch 가속기 확인 (설치되어 있는 경우)
    try:
        import torch
        if torch.cuda.is_available():
            backend_name = "AMD ROCm" if hasattr(torch.version, "hip") and torch.version.hip else "NVIDIA CUDA"
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                total_mem = round(torch.cuda.get_device_properties(i).total_memory / (1024 ** 3), 1)
                gpu_list.append({
                    "type": backend_name,
                    "name": name,
                    "vram_gb": total_mem,
                    "unified": False
                })
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            ram_gb = get_system_ram_gb() or 0
            gpu_list.append({
                "type": "Apple Silicon (Metal/MPS)",
                "name": f"Apple GPU ({platform.processor() or 'Apple Silicon'})",
                "vram_gb": ram_gb,  # 통합 메모리
                "unified": True
            })
        elif hasattr(torch, "xpu") and torch.xpu.is_available():
            for i in range(torch.xpu.device_count()):
                name = torch.xpu.get_device_name(i)
                total_mem = round(torch.xpu.get_device_properties(i).total_memory / (1024 ** 3), 1)
                gpu_list.append({
                    "type": "Intel XPU (oneAPI/SYCL)",
                    "name": name,
                    "vram_gb": total_mem,
                    "unified": False
                })
    except ImportError:
        pass

    # 2. PyTorch가 없거나 감지되지 않은 경우 OS별 수동 진단
    if not gpu_list:
        target_os = detect_os()
        
        # Windows / Linux: nvidia-smi CLI
        if "Windows" in target_os or "Linux" in target_os:
            try:
                cmd = ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
                flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                out = subprocess.check_output(cmd, creationflags=flags).decode().strip()
                for line in out.splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        gpu_list.append({
                            "type": "NVIDIA GPU",
                            "name": parts[0],
                            "vram_gb": round(float(parts[1]) / 1024, 1),
                            "unified": False
                        })
            except Exception:
                pass
                
            # Linux: AMD rocm-smi 확인
            if not gpu_list and "Linux" in target_os:
                try:
                    out = subprocess.check_output(["rocm-smi", "--showmeminfo", "vram"]).decode()
                    gpu_list.append({
                        "type": "AMD ROCm GPU",
                        "name": "AMD Radeon / Instinct",
                        "vram_gb": get_system_ram_gb() or 0,
                        "unified": False
                    })
                except Exception:
                    pass
                
        # macOS: system_profiler
        elif "macOS" in target_os:
            try:
                out = subprocess.check_output(["system_profiler", "SPDisplaysDataType"]).decode()
                chip_name = "Apple Silicon GPU"
                for line in out.splitlines():
                    if "Chipset Model:" in line:
                        chip_name = line.split(":", 1)[1].strip()
                        break
                ram_gb = get_system_ram_gb() or 0
                gpu_list.append({
                    "type": "Apple Silicon GPU",
                    "name": chip_name,
                    "vram_gb": ram_gb,
                    "unified": True
                })
            except Exception:
                pass
                
        # iOS / iPadOS: Apple Bionic / M-Series GPU (Unified Memory)
        elif any(k in target_os for k in ["iOS", "iPadOS"]):
            ram_gb = get_system_ram_gb() or 0
            gpu_list.append({
                "type": "Apple Metal GPU (Mobile Unified Memory)",
                "name": f"Apple A/M Series GPU ({target_os})",
                "vram_gb": ram_gb,
                "unified": True
            })

        # Android: CPU/AP 모델 기반 추론
        elif "Android" in target_os:
            gpu_name = "Mobile GPU (Adreno / Mali / Immortalis)"
            if os.path.exists("/proc/cpuinfo"):
                try:
                    with open("/proc/cpuinfo", "r") as f:
                        for line in f:
                            if "Hardware" in line or "model name" in line:
                                gpu_name = line.split(":", 1)[1].strip()
                                break
                except Exception:
                    pass
            gpu_list.append({
                "type": "Mobile GPU/NPU (Vulkan/NNAPI)",
                "name": gpu_name,
                "vram_gb": get_system_ram_gb() or 0,
                "unified": True
            })

    return gpu_list


def recommend_models(os_name, ram_gb, gpus):
    """사양 및 운영체제 특성 기반 최적 AI 모델 제안 매트릭스"""
    vram_gb = gpus[0]["vram_gb"] if gpus else 0
    is_unified = gpus[0]["unified"] if gpus else False
    is_mobile = any(k in os_name for k in ["Android", "iPadOS", "iOS"])

    recommendations = {
        "recommended_llm": [],
        "recommended_diffusion": [],
        "recommended_engines": []
    }

    # 1. 운영체제별 추천 실행 엔진
    if "Windows" in os_name:
        recommendations["recommended_engines"] = [
            "Ollama (간편한 로컬 LLM CLI/서버)",
            "LM Studio (사용자 친화적 GUI)",
            "vLLM (WSL2 고속 서빙)",
            "ComfyUI / Diffusers (이미지 생성 최적화)"
        ]
    elif "Linux" in os_name:
        recommendations["recommended_engines"] = [
            "vLLM (초고속 PagedAttention 기반 프로덕션 서빙)",
            "Ollama (원클릭 설치 및 서빙)",
            "TGI (Hugging Face Text Generation Inference)",
            "llama.cpp / Aphrodite Engine",
            "ComfyUI / Stable Diffusion WebUI (A1111, Forge)"
        ]
    elif "macOS" in os_name:
        recommendations["recommended_engines"] = [
            "Ollama (Apple Metal GPU 가속)",
            "LM Studio (Apple Silicon M시리즈 최적화)",
            "MLX / MLX-LM (애플 공식 고속 프레임워크)",
            "Draw Things (Metal 기반 고속 이미지 생성 앱)"
        ]
    elif "iPadOS" in os_name:
        recommendations["recommended_engines"] = [
            "Draw Things (App Store - 로컬 SD/FLUX 생성 앱)",
            "Layla (온디바이스 LLM 채팅 앱)",
            "Enchanted / Ollama Hub (Mac/PC 로컬 LLM 연동 클라이언트)"
        ]
    elif "iOS" in os_name:
        recommendations["recommended_engines"] = [
            "PocketPal AI (iOS 네이티브 온디바이스 LLM)",
            "Draw Things (아이폰 지원 온디바이스 생성 앱)",
            "Private LLM (보안 온디바이스 챗봇)",
            "Enchanted (홈서버 LLM 리모트 챗봇)"
        ]
    elif "Android" in os_name:
        recommendations["recommended_engines"] = [
            "Termux + Ollama / llama.cpp (안드로이드 리눅스 터미널)",
            "ChatterUI (GGUF 모델 로컬 로드 앱)",
            "MLC LLM (Qualcomm Snapdragon NPU/Vulkan 가속)"
        ]

    # 2. LLM 모델 크기 및 양자화 추천
    usable_mem = vram_gb if (vram_gb > 0 and not is_unified) else (ram_gb * 0.7 if ram_gb else 4)

    if usable_mem >= 24:
        recommendations["recommended_llm"].append("32B ~ 70B 모델 (Q4 양자화, 예: Qwen 2.5 32B, Llama 3.3 70B)")
        recommendations["recommended_llm"].append("14B 모델 (Q8 또는 FP16 풀정밀도)")
    elif usable_mem >= 14:
        recommendations["recommended_llm"].append("14B 모델 (Q4/Q5 양자화, 예: Qwen 2.5 14B, DeepSeek-R1-Distill-14B)")
        recommendations["recommended_llm"].append("8B 모델 (Q8 고정밀도)")
    elif usable_mem >= 8:
        recommendations["recommended_llm"].append("7B ~ 8B 모델 (Q4/Q5 양자화, 예: Llama 3.1 8B, Qwen 2.5 7B, Gemma 2 9B)")
        recommendations["recommended_llm"].append("3B ~ 4B 모델 (Q8 고정밀도, 예: Llama 3.2 3B, Phi-3.5)")
    elif usable_mem >= 5:
        recommendations["recommended_llm"].append("3B ~ 4B 초경량 온디바이스 모델 (Q4 양자화, 예: Llama 3.2 3B, Qwen 2.5 3B)")
        recommendations["recommended_llm"].append("1B ~ 1.5B 초고속 모델 (예: Qwen 2.5 1.5B, SmolLM2 1.7B)")
    else:
        recommendations["recommended_llm"].append("1B 미만 ~ 1.5B 모바일 초경량 모델 (Q4, 예: SmolLM2 360M/1.7B, Qwen 2.5 0.5B/1.5B)")

    # 3. 이미지 생성 (Diffusion / FLUX) 모델 추천
    if is_mobile:
        if usable_mem >= 6:
            recommendations["recommended_diffusion"].append("SD 1.5 기반 경량 체크포인트 (Draw Things 앱으로 512x512 생성)")
            recommendations["recommended_diffusion"].append("SDXL-Turbo / LCM (4~8스텝 실시간 생성)")
        else:
            recommendations["recommended_diffusion"].append("스마트폰/태블릿 메모리 제약으로 로컬 생성보다는 Cloud API 권장")
    else:
        if vram_gb >= 16 or (is_unified and ram_gb >= 32):
            recommendations["recommended_diffusion"].append("FLUX.1 [dev] / FLUX.2 Klein (1024x1024 ~ 1536x1536 고화질)")
            recommendations["recommended_diffusion"].append("SDXL 1.0 (FP16 풀옵션, ComfyUI/Diffusers)")
            recommendations["recommended_diffusion"].append("SD 3.5 Large (8B DiT)")
        elif vram_gb >= 10 or (is_unified and ram_gb >= 16):
            recommendations["recommended_diffusion"].append("FLUX.2 [klein] 4B (4스텝 초고속, CPU Offload + VAE Tiling 적용 시 1536x1536 지원)")
            recommendations["recommended_diffusion"].append("SDXL (FP16, 1024x1024 해상도)")
            recommendations["recommended_diffusion"].append("SD 1.5 고품질 체크포인트 (CyberRealistic 등, 1024x1024 업스케일링 가능)")
        elif vram_gb >= 6:
            recommendations["recommended_diffusion"].append("SD 1.5 (512x512 ~ 768x768 기본 해상도 최적)")
            recommendations["recommended_diffusion"].append("SDXL-Turbo / Lightning (FP16, 4스텝 고속 생성)")
        else:
            recommendations["recommended_diffusion"].append("SD 1.5 (CPU Offload 및 Attention Slicing 필수, 512x512)")

    return recommendations


def format_markdown_report(os_name, ram_gb, gpus, recs):
    """결과를 깔끔한 Markdown(.md) 문서 형식으로 포맷팅"""
    gpu_lines = ""
    if gpus:
        for idx, g in enumerate(gpus, 1):
            unified_str = " (통합 메모리/Unified)" if g['unified'] else ""
            gpu_lines += f"- **가속기 {idx}**: {g['name']} ({g['type']}) - 가용 VRAM: **{g['vram_gb']} GB**{unified_str}\n"
    else:
        gpu_lines = "- **가속기**: 전용 외장 GPU 미감지 (CPU 모드)\n"

    llm_lines = "\n".join([f"- [x] {m}" for m in recs["recommended_llm"]])
    diff_lines = "\n".join([f"- [x] {d}" for m in recs["recommended_diffusion"] for d in [m]])
    eng_lines = "\n".join([f"- {e}" for e in recs["recommended_engines"]])

    md = f"""# 🔍 AI 모델 구동 환경 진단 보고서

> 지원 플랫폼: Windows, macOS, Linux, iOS, iPadOS, Android

## 1. 하드웨어 및 시스템 사양
- **운영체제(OS)**: `{os_name}` ({platform.platform()})
- **프로세서(CPU)**: `{platform.processor() or platform.machine()}`
- **시스템 RAM**: **{ram_gb if ram_gb else '측정 불가'} GB**
{gpu_lines}
---

## 2. 권장 최적 AI 모델 제안

### 💡 [1] 추천 텍스트 LLM (언어 모델)
{llm_lines}

### 🎨 [2] 추천 이미지 생성 모델 (Diffusion / FLUX)
{diff_lines}

### ⚡ [3] 추천 로컬 실행 엔진 및 툴
{eng_lines}
"""
    return md


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI 모델 구동 환경 진단 및 파일 저장 도구 (Windows/macOS/Linux/iOS/iPadOS/Android)")
    parser.add_argument("--output", "-o", type=str, default="ai_env_report.md", help="저장할 파일 경로 (.md 또는 .txt)")
    parser.add_argument("--no-save", action="store_true", help="파일 저장 없이 콘솔에만 출력")
    args = parser.parse_args()

    os_name = detect_os()
    ram_gb = get_system_ram_gb()
    gpus = get_gpu_info()
    recs = recommend_models(os_name, ram_gb, gpus)

    # 콘솔 출력용 텍스트 구성
    console_output = []
    console_output.append("=" * 65)
    console_output.append("      🔍 AI 모델(LLM & Diffusion) 구동 환경 정밀 진단 결과")
    console_output.append("=" * 65)
    console_output.append(f" • 운영체제(OS)     : {os_name} ({platform.platform()})")
    console_output.append(f" • 프로세서(CPU)    : {platform.processor() or platform.machine()}")
    console_output.append(f" • 시스템 RAM       : {ram_gb if ram_gb else '측정 불가'} GB")
    
    if gpus:
        for idx, g in enumerate(gpus, 1):
            unified_str = " (통합 메모리/Unified)" if g['unified'] else ""
            console_output.append(f" • 가속기(GPU {idx})  : {g['name']} [{g['type']}]")
            console_output.append(f"   - 가용 VRAM      : {g['vram_gb']} GB{unified_str}")
    else:
        console_output.append(" • 가속기(GPU)      : 전용 외장 GPU 미감지 (CPU/통합 그래픽 모드)")

    console_output.append("-" * 65)
    console_output.append("  💡 최적 구동 가능 AI 모델 제안")
    console_output.append("-" * 65)
    
    console_output.append(" [1] 추천 텍스트 LLM:")
    for m in recs["recommended_llm"]:
        console_output.append(f"     ✅ {m}")

    console_output.append("\n [2] 추천 이미지 생성 모델:")
    for d in recs["recommended_diffusion"]:
        console_output.append(f"     🎨 {d}")

    console_output.append("\n [3] 추천 로컬 실행 엔진 / 도구:")
    for e in recs["recommended_engines"]:
        console_output.append(f"     ⚡ {e}")
    console_output.append("=" * 65)

    full_console_text = "\n".join(console_output)
    print(full_console_text)

    # 파일 저장 처리
    if not args.no_save:
        output_path = args.output
        is_md = output_path.lower().endswith(".md")
        
        if is_md:
            file_content = format_markdown_report(os_name, ram_gb, gpus, recs)
        else:
            file_content = full_console_text

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            print(f"\n📄 진단 결과가 성공적으로 저장되었습니다: {os.path.abspath(output_path)}")
        except Exception as e:
            print(f"\n⚠️ 파일 저장 실패: {e}")


if __name__ == "__main__":
    main()
