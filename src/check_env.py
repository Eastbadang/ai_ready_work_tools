"""
AI 모델(LLM 및 이미지 생성 모델) 선정을 위한 크로스 플랫폼 환경 진단 도구
지원 OS: Windows, macOS, iPadOS(a-Shell/Pythonista), Android(Termux/Pydroid3)
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
    """운영체제 세부 판별 (Windows, macOS, iPadOS/iOS, Android, Linux)"""
    sys_name = platform.system().lower()
    
    # 1. Android 확인 (Termux, Pydroid 등)
    if "android" in sys.platform.lower() or os.path.exists("/system/build.prop") or "ANDROID_ROOT" in os.environ:
        return "Android"
    
    # 2. iPadOS / iOS 확인 (Pythonista, a-Shell, iSH 등)
    if sys_name == "darwin":
        machine = platform.machine()
        if "ipad" in machine.lower() or "iphone" in machine.lower():
            return "iPadOS" if "ipad" in machine.lower() else "iOS"
        # iSH or sandbox app detection
        if os.path.exists("/private/var/mobile"):
            return "iPadOS / iOS"
        return "macOS"
    
    # 3. Windows
    if sys_name == "windows":
        return "Windows"
    
    # 4. 기타 Linux
    if sys_name == "linux":
        return "Linux"
        
    return sys_name.capitalize()


def get_system_ram_gb():
    """시스템 RAM(GB) 측정 (OS별 표준 명령 및 /proc 활용)"""
    # 1. psutil이 있으면 가장 정확
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except ImportError:
        pass

    target_os = detect_os()

    # 2. Windows: ctypes (GlobalMemoryStatusEx)
    if target_os == "Windows":
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

    # 3. macOS / iPadOS: sysctl hw.memsize
    if target_os in ["macOS", "iPadOS", "iOS"]:
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).decode().strip()
            return round(int(out) / (1024 ** 3), 1)
        except Exception:
            pass

    # 4. Android / Linux: /proc/meminfo
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
    """GPU / NPU 및 VRAM 측정 (NVIDIA, Apple Silicon Metal, Vulkan/OpenCL 등)"""
    gpu_list = []
    
    # 1. PyTorch 기반 가속기 확인 (설치되어 있는 경우)
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                name = torch.cuda.get_device_name(i)
                total_mem = round(torch.cuda.get_device_properties(i).total_memory / (1024 ** 3), 1)
                gpu_list.append({
                    "type": "NVIDIA CUDA",
                    "name": name,
                    "vram_gb": total_mem,
                    "unified": False
                })
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # Apple Silicon Unified Memory
            ram_gb = get_system_ram_gb() or 0
            gpu_list.append({
                "type": "Apple Silicon (Metal/MPS)",
                "name": f"Apple GPU ({platform.processor() or 'Apple Silicon'})",
                "vram_gb": ram_gb,  # 통합 메모리
                "unified": True
            })
    except ImportError:
        pass

    # PyTorch로 확인되지 않은 경우 OS별 수동 진단
    if not gpu_list:
        target_os = detect_os()
        
        # Windows: nvidia-smi 확인
        if target_os == "Windows":
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                ).decode().strip()
                for line in out.splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        name = parts[0]
                        vram = round(float(parts[1]) / 1024, 1)
                        gpu_list.append({
                            "type": "NVIDIA GPU",
                            "name": name,
                            "vram_gb": vram,
                            "unified": False
                        })
            except Exception:
                pass
                
        # macOS: system_profiler
        elif target_os == "macOS":
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
                
        # Android: Adreno / Mali / Vulkan 확인 시도
        elif target_os == "Android":
            gpu_name = "Mobile GPU (Adreno / Mali)"
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
    """하드웨어 스펙 기반 최적 AI 모델(LLM 및 이미지 모델) 추천 매트릭스"""
    vram_gb = gpus[0]["vram_gb"] if gpus else 0
    is_unified = gpus[0]["unified"] if gpus else False
    is_mobile = os_name in ["Android", "iPadOS", "iOS"]

    recommendations = {
        "recommended_llm": [],
        "recommended_diffusion": [],
        "recommended_engines": []
    }

    # 1. 실행 엔진 추천
    if os_name == "Windows":
        recommendations["recommended_engines"] = ["Ollama", "LM Studio", "vLLM (WSL2)", "Diffusers / ComfyUI"]
    elif os_name == "macOS":
        recommendations["recommended_engines"] = ["Ollama (Metal)", "LM Studio (Apple Silicon)", "MLX (Apple 공식)", "Draw Things (Metal)"]
    elif os_name == "iPadOS":
        recommendations["recommended_engines"] = ["Draw Things (App Store)", "Layla", "Enchanted (Ollama 클라이언트)"]
    elif os_name == "Android":
        recommendations["recommended_engines"] = ["Termux + Ollama / llama.cpp", "ChatterUI", "MLC LLM"]

    # 2. LLM 모델 추천
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
    else:
        recommendations["recommended_llm"].append("1B ~ 3B 초경량 온디바이스 모델 (Q4 양자화, 예: Llama 3.2 1B/3B, Qwen 2.5 1.5B/3B, SmolLM2)")

    # 3. 이미지 생성 (Diffusion) 모델 추천
    if is_mobile:
        if usable_mem >= 6:
            recommendations["recommended_diffusion"].append("SD 1.5 기반 경량 모델 (Draw Things / Mobile App)")
            recommendations["recommended_diffusion"].append("SDXL-Turbo / LCM (저스텝 4~8스텝 실시간 생성)")
        else:
            recommendations["recommended_diffusion"].append("모바일 VRAM 제약으로 온디바이스 고화질 생성은 제한적 (Cloud API 권장)")
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

> 생성 일시: 시스템 로컬 타임 기준 자동 생성

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
    parser = argparse.ArgumentParser(description="AI 모델 구동 환경 진단 및 파일 저장 도구")
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
