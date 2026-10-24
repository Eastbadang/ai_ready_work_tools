"""
AnimateDiff (SD 1.5) 기반 텍스트-투-비디오(Text-to-Video) 로컬 파이프라인
- 로컬 체크포인트: models/CyberRealistic_FINAL_FP16.safetensors
- 모션 어댑터: guoyww/animatediff-motion-adapter-v1-5-2
- 하드웨어: RTX 3060 (12GB VRAM) 최적화 (Model CPU Offload & VAE Slicing)
"""

import os
import sys
import warnings
import argparse
import torch

# 불필요한 경고 억제
os.environ["XFORMERS_MORE_DETAILS"] = "0"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from diffusers import (
    AnimateDiffPipeline,
    MotionAdapter,
    DPMSolverMultistepScheduler
)
from diffusers.utils import export_to_video, export_to_gif


def run_animatediff(
    base_model_path: str = "models/CyberRealistic_FINAL_FP16.safetensors",
    motion_adapter_id: str = "guoyww/animatediff-motion-adapter-v1-5-2",
    prompt: str = (
        "(masterpiece, best quality:1.3), an athletic marathon runner sprinting through a city street, "
        "crossing the finish line, arms raised in victory, celebratory confetti falling, "
        "dynamic camera panning, cinematic lighting, 8k, photorealistic"
    ),
    negative_prompt: str = (
        "(worst quality, low quality:1.4), (deformed, bad anatomy, bad hands, missing limbs:1.3), "
        "blurry, static image, jumpy motion, watermark, text"
    ),
    num_frames: int = 16,
    fps: int = 8,
    width: int = 512,
    height: int = 512,
    steps: int = 25,
    guidance_scale: float = 7.5,
    seed: int = 42,
    output_filename: str = "outputs/animatediff_result.mp4"
):
    if not torch.cuda.is_available():
        raise RuntimeError("NVIDIA CUDA 가속기가 필요합니다.")

    device_name = torch.cuda.get_device_name(0)
    print(f"[1/4] 사용 디바이스: {device_name}")
    print(f"       설정: {width}x{height}, {num_frames} 프레임 (@ {fps} fps), 시드: {seed}")

    # 1. 모션 어댑터 로드
    print(f"[2/4] 모션 어댑터({motion_adapter_id}) 로드 중...")
    adapter = MotionAdapter.from_pretrained(
        motion_adapter_id,
        torch_dtype=torch.float16
    )

    # 2. 로컬 SD 1.5 베이스 체크포인트와 결합하여 파이프라인 구성
    print(f"       로컬 베이스 모델({base_model_path})과 결합 중...")
    if not os.path.exists(base_model_path):
        raise FileNotFoundError(f"베이스 모델을 찾을 수 없습니다: {base_model_path}")

    pipe = AnimateDiffPipeline.from_single_file(
        base_model_path,
        motion_adapter=adapter,
        torch_dtype=torch.float16,
        safety_checker=None  # 연구 및 로컬 환경용 세이프티 필터 해제
    )

    # 3. 고속 스케줄러 및 VRAM 최적화
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        beta_schedule="linear",
        algorithm_type="dpmsolver++",
        use_karras_sigmas=True
    )

    # RTX 3060 12GB 환경을 위한 필수 VRAM 최적화
    print("       [최적화] Model CPU Offload 및 Attention Slicing 활성화...")
    pipe.enable_model_cpu_offload()
    pipe.enable_attention_slicing()
    if hasattr(pipe, "vae") and hasattr(pipe.vae, "enable_slicing"):
        pipe.vae.enable_slicing()

    # 4. 비디오 생성 (추론)
    generator = torch.Generator(device="cuda").manual_seed(seed)
    print(f"[3/4] 비디오 프레임({num_frames}장) 생성 시작...")

    with torch.inference_mode():
        output = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_frames=num_frames,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            generator=generator
        )

    frames = output.frames[0]

    # 5. 비디오/GIF 파일 저장
    out_dir = os.path.dirname(os.path.abspath(output_filename))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print(f"[4/4] 비디오 파일 인코딩 및 저장 중: {output_filename}")
    if output_filename.lower().endswith(".gif"):
        export_to_gif(frames, output_filename)
    else:
        # mp4 저장
        export_to_video(frames, output_filename, fps=fps)

    vram_used = torch.cuda.max_memory_allocated() / (1024 ** 2)
    print(f"[OK] 비디오 생성 완료: {os.path.abspath(output_filename)}")
    print(f"     최대 VRAM 사용량: {vram_used:.2f} MB / 12288 MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnimateDiff Text-to-Video Generator for SD 1.5")
    parser.add_argument("--model", type=str, default="models/CyberRealistic_FINAL_FP16.safetensors", help="SD 1.5 모델 체크포인트 경로")
    parser.add_argument("--prompt", type=str, default=None, help="비디오 생성 프롬프트")
    parser.add_argument("--negative-prompt", type=str, default=None, help="네거티브 프롬프트")
    parser.add_argument("--frames", type=int, default=16, help="생성할 프레임 수 (기본: 16)")
    parser.add_argument("--fps", type=int, default=8, help="초당 프레임 수 (기본: 8)")
    parser.add_argument("--width", type=int, default=512, help="비디오 너비 (기본: 512)")
    parser.add_argument("--height", type=int, default=512, help="비디오 높이 (기본: 512)")
    parser.add_argument("--steps", type=int, default=25, help="추론 스텝 (기본: 25)")
    parser.add_argument("--scale", type=float, default=7.5, help="CFG Scale (기본: 7.5)")
    parser.add_argument("--seed", type=int, default=42, help="랜덤 시드 (기본: 42)")
    parser.add_argument("--output", type=str, default="outputs/animatediff_result.mp4", help="저장할 파일 경로 (.mp4 또는 .gif)")

    args = parser.parse_args()

    kwargs = {
        "base_model_path": args.model,
        "num_frames": args.frames,
        "fps": args.fps,
        "width": args.width,
        "height": args.height,
        "steps": args.steps,
        "guidance_scale": args.scale,
        "seed": args.seed,
        "output_filename": args.output,
    }
    if args.prompt:
        kwargs["prompt"] = args.prompt
    if args.negative_prompt:
        kwargs["negative_prompt"] = args.negative_prompt

    run_animatediff(**kwargs)
