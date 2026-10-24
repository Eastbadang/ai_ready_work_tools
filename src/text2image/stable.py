import os
import sys
import warnings
import re
import argparse
from typing import Dict, Any, Optional

# xformers / Triton 및 diffusers 경고 로그 억제
os.environ["XFORMERS_MORE_DETAILS"] = "0"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import torch
from diffusers import (
    Flux2KleinPipeline,
    Flux2Transformer2DModel,
    StableDiffusionPipeline,
    DPMSolverMultistepScheduler
)


def resolve_model_path(model_path: str) -> str:
    """상대 경로인 경우 스크립트 위치 기준으로 절대 경로 확인"""
    if not os.path.isabs(model_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(base_dir, model_path)
        if os.path.exists(candidate):
            return candidate
    return model_path


def is_flux_model(model_path: str) -> bool:
    """파일명 또는 경로에 'flux'가 포함되어 있는지 여부로 FLUX 모델 여부 판별"""
    return "flux" in model_path.lower()


def load_flux_klein_pipeline(local_model_path: str) -> Flux2KleinPipeline:
    """FLUX.2 Klein 4B 단일 트랜스포머 가중치와 공식 허브 컴포넌트를 결합하여 로드"""
    resolved_path = resolve_model_path(local_model_path)
    dtype = torch.bfloat16
    hf_repo_id = "black-forest-labs/FLUX.2-klein-4B"

    print(f"[2/4] FLUX.2 Klein 로컬 트랜스포머 가중치 로드 중: {os.path.abspath(resolved_path)}")
    transformer = Flux2Transformer2DModel.from_single_file(
        resolved_path,
        config=hf_repo_id,
        subfolder="transformer",
        torch_dtype=dtype
    )

    print(f"       허브({hf_repo_id})에서 Text Encoder 및 VAE 컴포넌트 로드 중...")
    pipe = Flux2KleinPipeline.from_pretrained(
        hf_repo_id,
        transformer=transformer,
        torch_dtype=dtype
    )

    print("       [최적화] 32GB RAM 활용을 위한 Model CPU Offload 활성화...")
    pipe.enable_model_cpu_offload()

    if hasattr(pipe, "vae"):
        print("       [최적화] 초고해상도 출력을 위한 VAE Tiling & Slicing 활성화...")
        pipe.vae.enable_tiling()
        pipe.vae.enable_slicing()

    pipe.enable_attention_slicing()
    return pipe


def load_sd15_pipeline(model_path: str, device: str = "cuda") -> StableDiffusionPipeline:
    """SD 1.5 계열 모델 로드 및 최적화"""
    resolved_path = resolve_model_path(model_path)
    print(f"[2/4] SD 1.5 모델 로드 중: {os.path.abspath(resolved_path)}")
    if os.path.isfile(resolved_path):
        pipe = StableDiffusionPipeline.from_single_file(
            resolved_path,
            torch_dtype=torch.float16,
            safety_checker=None
        )
    else:
        pipe = StableDiffusionPipeline.from_pretrained(
            resolved_path,
            torch_dtype=torch.float16,
            use_safetensors=True
        )

    pipe.scheduler = DPMSolverMultistepScheduler.from_config(
        pipe.scheduler.config,
        use_karras_sigmas=True
    )
    pipe = pipe.to(device)
    pipe.enable_attention_slicing()
    return pipe


def run_generation(
    model_path: str = "models/CyberRealistic_FINAL_FP16.safetensors",
    prompt: str = (
        "masterpiece, best quality, ultra-detailed, a futuristic cyberpunk laboratory "
        "with holographic displays, glowing neon circuits, cinematic lighting, 8k resolution"
    ),
    negative_prompt: Optional[str] = None,
    width: int = 512,
    height: int = 512,
    steps: int = 25,
    guidance_scale: float = 7.5,
    seed: int = 42,
    output_filename: str = "output_result.png",
    callback: Optional[Any] = None
) -> str:
    """통합 이미지 추론 함수"""
    if not torch.cuda.is_available():
        raise RuntimeError("NVIDIA GPU(CUDA)가 감지되지 않았습니다. PyTorch 설정을 확인하세요.")

    device_name = torch.cuda.get_device_name(0)
    print(f"[1/4] 사용 GPU: {device_name}")
    print(f"       설정 해상도: {width} x {height} (약 {(width * height) / 1_000_000:.2f} MegaPixels)")

    resolved_model_path = resolve_model_path(model_path)
    if not os.path.exists(resolved_model_path):
        raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {resolved_model_path}")

    torch.cuda.empty_cache()
    if seed == -1:
        import random
        seed = random.randint(0, 2**32 - 1)
        print(f"       [Random Seed] 무작위 시드 생성: {seed}")

    generator = torch.Generator(device="cuda").manual_seed(seed)

    if is_flux_model(resolved_model_path):
        pipe = load_flux_klein_pipeline(resolved_model_path)
        flux_steps = steps if steps <= 8 else 4
        flux_scale = guidance_scale if guidance_scale <= 2.0 else 1.0
        print(f"[3/4] FLUX.2 Klein 이미지 생성 시작 (스텝: {flux_steps}, CFG: {flux_scale}, 시드: {seed})...")
        with torch.inference_mode():
            output = pipe(
                prompt=prompt,
                height=height,
                width=width,
                num_inference_steps=flux_steps,
                guidance_scale=flux_scale,
                generator=generator
            )
    else:
        pipe = load_sd15_pipeline(resolved_model_path, device="cuda")
        neg_prompt = negative_prompt or "low quality, worst quality, blurry, deformed, bad anatomy, watermark, text"
        sd_steps = steps if steps >= 10 else 25
        sd_scale = guidance_scale if guidance_scale >= 2.0 else 7.5
        print(f"[3/4] SD 1.5 이미지 생성 시작 (스텝: {sd_steps}, CFG: {sd_scale}, 시드: {seed})...")
        with torch.inference_mode():
            output = pipe(
                prompt=prompt,
                negative_prompt=neg_prompt,
                height=height,
                width=width,
                num_inference_steps=sd_steps,
                guidance_scale=sd_scale,
                generator=generator
            )

    result_image = output.images[0]
    
    # 저장 경로의 상위 디렉터리가 없으면 자동 생성
    out_dir = os.path.dirname(os.path.abspath(output_filename))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    result_image.save(output_filename)

    vram_used = torch.cuda.max_memory_allocated() / (1024 ** 2)
    saved_abs_path = os.path.abspath(output_filename)
    print(f"[4/4] 이미지 생성 완료! 파일 저장: {saved_abs_path}")
    print(f"       최대 VRAM 사용량: {vram_used:.2f} MB / 12288 MB")

    if callback:
        callback(saved_abs_path)

    return saved_abs_path


def parse_input_file(file_path: str) -> Dict[str, Any]:
    """
    텍스트 파일(.txt) 또는 마크다운 파일(.md)에서 프롬프트 및 설정 파싱
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    params: Dict[str, Any] = {}

    # 정규식 기반 마크다운 섹션 파싱 (# Prompt, # Negative, # Settings 등)
    prompt_match = re.search(r"(?:^|\n)#+\s*Prompt\s*\n(.*?)(?=\n#+|$)", content, re.IGNORECASE | re.DOTALL)
    neg_match = re.search(r"(?:^|\n)#+\s*Negative(?:\s*Prompt)?\s*\n(.*?)(?=\n#+|$)", content, re.IGNORECASE | re.DOTALL)
    settings_match = re.search(r"(?:^|\n)#+\s*Settings\s*\n(.*?)(?=\n#+|$)", content, re.IGNORECASE | re.DOTALL)

    if prompt_match:
        params["prompt"] = prompt_match.group(1).strip()
    else:
        # 섹션 헤더가 없는 일반 텍스트 파일인 경우 전체 내용을 프롬프트로 사용
        params["prompt"] = content.strip()

    if neg_match:
        params["negative_prompt"] = neg_match.group(1).strip()

    if settings_match:
        settings_text = settings_match.group(1)
        for line in settings_text.splitlines():
            line = line.strip().lstrip("-* ").strip()
            if ":" in line:
                k, v = [x.strip() for x in line.split(":", 1)]
                k = k.lower().replace(" ", "_")
                if k in ["width", "height", "steps", "seed"]:
                    try:
                        params[k] = int(v)
                    except ValueError:
                        pass
                elif k in ["scale", "guidance_scale"]:
                    try:
                        params["guidance_scale"] = float(v)
                    except ValueError:
                        pass
                elif k in ["model", "model_path"]:
                    params["model_path"] = v
                elif k in ["output", "output_filename"]:
                    params["output_filename"] = v

    return params


def launch_qt6_gui():
    """PySide6 기반 Qt6 GUI 윈도우 실행"""
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox,
        QPushButton, QFileDialog, QComboBox, QMessageBox, QFrame,
        QScrollArea, QProgressBar
    )
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QPixmap, QFont

    class WorkerThread(QThread):
        finished_signal = Signal(str)
        error_signal = Signal(str)

        def __init__(self, kwargs):
            super().__init__()
            self.kwargs = kwargs

        def run(self):
            try:
                res_path = run_generation(**self.kwargs)
                self.finished_signal.emit(res_path)
            except Exception as e:
                self.error_signal.emit(str(e))

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("🎨 Stable Diffusion & FLUX.2 Studio (Qt6)")
            self.resize(1000, 750)

            # 탐색 가능한 모델 목록
            self.models = [
                "models/CyberRealistic_FINAL_FP16.safetensors",
                "models/CyberRealisticXLPlay_V10.0_FP16.safetensors",
                "models/flux-2-klein-4b.safetensors",
            ]

            main_widget = QWidget()
            self.setCentralWidget(main_widget)
            root_layout = QHBoxLayout(main_widget)

            # [좌측] 입력 및 설정 패널
            left_panel = QWidget()
            left_layout = QVBoxLayout(left_panel)
            left_panel.setFixedWidth(500)

            # 1. 파일 불러오기 버튼
            file_btn_layout = QHBoxLayout()
            self.btn_load_file = QPushButton("📂 프롬프트/설정 파일 불러오기 (.md, .txt)")
            self.btn_load_file.setStyleSheet("background-color: #3b82f6; color: white; padding: 6px; font-weight: bold; border-radius: 4px;")
            self.btn_load_file.clicked.connect(self.on_load_file)
            file_btn_layout.addWidget(self.btn_load_file)
            left_layout.addLayout(file_btn_layout)

            # 2. 모델 선택
            left_layout.addWidget(QLabel("<b>모델 선택:</b>"))
            model_layout = QHBoxLayout()
            self.combo_model = QComboBox()
            for m in self.models:
                self.combo_model.addItem(m)
            self.combo_model.setCurrentIndex(0)
            model_layout.addWidget(self.combo_model)

            self.btn_browse_model = QPushButton("찾아보기...")
            self.btn_browse_model.clicked.connect(self.on_browse_model)
            model_layout.addWidget(self.btn_browse_model)
            left_layout.addLayout(model_layout)

            # 3. 긍정 프롬프트
            left_layout.addWidget(QLabel("<b>긍정 프롬프트 (Prompt):</b>"))
            self.txt_prompt = QTextEdit()
            self.txt_prompt.setPlaceholderText("생성할 이미지에 대한 상세 설명을 입력하세요...")
            self.txt_prompt.setText(
                "(masterpiece, best quality, ultra-detailed, photorealistic:1.35), dynamic action shot of an athletic marathon runner "
                "crossing the finish line in first place, breaking the red finish line tape with chest, arms raised in victory, "
                "emotional triumphant expression, athletic running wear, cheering crowd, city street marathon, confetti, morning sunlight, 8k, professional sports photography"
            )
            self.txt_prompt.setFixedHeight(120)
            left_layout.addWidget(self.txt_prompt)

            # 4. 부정 프롬프트
            left_layout.addWidget(QLabel("<b>부정 프롬프트 (Negative Prompt - SD 전용):</b>"))
            self.txt_neg_prompt = QTextEdit()
            self.txt_neg_prompt.setPlaceholderText("제외할 요소들을 입력하세요...")
            self.txt_neg_prompt.setText(
                "(worst quality, low quality:1.4), (deformed, bad anatomy, unnatural pose, twisted body, malformed limbs, disconnected limbs, bad proportions:1.4), "
                "(mutated hands and fingers:1.3), blurry, cartoon, illustration, watermark, text"
            )
            self.txt_neg_prompt.setFixedHeight(75)
            left_layout.addWidget(self.txt_neg_prompt)

            # 5. 생성 파라미터 (해상도, 스텝, CFG, 시드)
            param_layout = QHBoxLayout()
            
            # Width & Height
            vbox_w = QVBoxLayout()
            vbox_w.addWidget(QLabel("너비(Width):"))
            self.spin_width = QSpinBox()
            self.spin_width.setRange(256, 2048)
            self.spin_width.setSingleStep(64)
            self.spin_width.setValue(832)
            vbox_w.addWidget(self.spin_width)
            param_layout.addLayout(vbox_w)

            vbox_h = QVBoxLayout()
            vbox_h.addWidget(QLabel("높이(Height):"))
            self.spin_height = QSpinBox()
            self.spin_height.setRange(256, 2048)
            self.spin_height.setSingleStep(64)
            self.spin_height.setValue(512)
            vbox_h.addWidget(self.spin_height)
            param_layout.addLayout(vbox_h)

            # Steps
            vbox_s = QVBoxLayout()
            vbox_s.addWidget(QLabel("스텝(Steps):"))
            self.spin_steps = QSpinBox()
            self.spin_steps.setRange(1, 100)
            self.spin_steps.setValue(25)
            vbox_s.addWidget(self.spin_steps)
            param_layout.addLayout(vbox_s)

            # Scale
            vbox_cfg = QVBoxLayout()
            vbox_cfg.addWidget(QLabel("CFG Scale:"))
            self.spin_scale = QDoubleSpinBox()
            self.spin_scale.setRange(1.0, 20.0)
            self.spin_scale.setSingleStep(0.5)
            self.spin_scale.setValue(7.5)
            vbox_cfg.addWidget(self.spin_scale)
            param_layout.addLayout(vbox_cfg)

            left_layout.addLayout(param_layout)

            # 6. 시드 및 출력 파일명
            seed_out_layout = QHBoxLayout()
            vbox_seed = QVBoxLayout()
            vbox_seed.addWidget(QLabel("시드 (Seed, -1은 무작위):"))
            self.spin_seed = QSpinBox()
            self.spin_seed.setRange(-1, 2147483647)
            self.spin_seed.setValue(1004)
            vbox_seed.addWidget(self.spin_seed)
            seed_out_layout.addLayout(vbox_seed)

            # 저장 경로 및 변경 버튼
            vbox_out = QVBoxLayout()
            vbox_out.addWidget(QLabel("저장 경로 (파일명 포함):"))
            out_file_row = QHBoxLayout()
            self.edit_output = QLineEdit("outputs/gui_result.png")
            out_file_row.addWidget(self.edit_output)

            self.btn_browse_output = QPushButton("경로 변경...")
            self.btn_browse_output.clicked.connect(self.on_browse_output)
            out_file_row.addWidget(self.btn_browse_output)
            vbox_out.addLayout(out_file_row)
            seed_out_layout.addLayout(vbox_out)

            left_layout.addLayout(seed_out_layout)

            # 7. 생성 버튼 & 진행률
            self.btn_generate = QPushButton("🚀 이미지 생성 시작 (Generate)")
            self.btn_generate.setFixedHeight(45)
            self.btn_generate.setStyleSheet("background-color: #10b981; color: white; font-size: 15px; font-weight: bold; border-radius: 6px;")
            self.btn_generate.clicked.connect(self.on_generate)
            left_layout.addWidget(self.btn_generate)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 0)  # 무한 로딩 인디케이터
            self.progress_bar.setVisible(False)
            left_layout.addWidget(self.progress_bar)

            self.lbl_status = QLabel("준비 완료.")
            self.lbl_status.setStyleSheet("color: #64748b;")
            left_layout.addWidget(self.lbl_status)

            root_layout.addWidget(left_panel)

            # [우측] 이미지 미리보기 패널
            right_panel = QFrame()
            right_panel.setFrameShape(QFrame.StyledPanel)
            right_layout = QVBoxLayout(right_panel)

            right_header = QHBoxLayout()
            right_header.addWidget(QLabel("<b>🖼️ 생성 결과 미리보기:</b>"))
            self.btn_open_folder = QPushButton("📁 저장 폴더 열기")
            self.btn_open_folder.setEnabled(False)
            self.btn_open_folder.clicked.connect(self.on_open_output_folder)
            right_header.addWidget(self.btn_open_folder)
            right_layout.addLayout(right_header)

            self.scroll_area = QScrollArea()
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setAlignment(Qt.AlignCenter)

            self.lbl_preview = QLabel("생성된 이미지가 여기에 표시됩니다.")
            self.lbl_preview.setAlignment(Qt.AlignCenter)
            self.lbl_preview.setStyleSheet("color: #94a3b8; font-size: 14px;")
            self.scroll_area.setWidget(self.lbl_preview)
            right_layout.addWidget(self.scroll_area)

            root_layout.addWidget(right_panel)

        def on_browse_output(self):
            path, _ = QFileDialog.getSaveFileName(
                self, "저장할 이미지 경로 및 파일명 지정",
                self.edit_output.text(),
                "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)"
            )
            if path:
                self.edit_output.setText(path)

        def on_open_output_folder(self):
            out_path = os.path.abspath(self.edit_output.text().strip())
            out_dir = os.path.dirname(out_path)
            if os.path.exists(out_dir):
                if sys.platform == "win32":
                    os.startfile(out_dir)
                elif sys.platform == "darwin":
                    subprocess.run(["open", out_dir])
                else:
                    subprocess.run(["xdg-open", out_dir])

        def on_browse_model(self):
            path, _ = QFileDialog.getOpenFileName(self, "체크포인트 모델 선택", "models", "Model Files (*.safetensors *.ckpt)")
            if path:
                if path not in self.models:
                    self.models.append(path)
                    self.combo_model.addItem(path)
                self.combo_model.setCurrentText(path)

        def on_load_file(self):
            path, _ = QFileDialog.getOpenFileName(self, "프롬프트 파일 열기", "", "Markdown / Text Files (*.md *.txt);;All Files (*)")
            if path:
                try:
                    data = parse_input_file(path)
                    if "prompt" in data:
                        self.txt_prompt.setText(data["prompt"])
                    if "negative_prompt" in data:
                        self.txt_neg_prompt.setText(data["negative_prompt"])
                    if "width" in data:
                        self.spin_width.setValue(data["width"])
                    if "height" in data:
                        self.spin_height.setValue(data["height"])
                    if "steps" in data:
                        self.spin_steps.setValue(data["steps"])
                    if "guidance_scale" in data:
                        self.spin_scale.setValue(data["guidance_scale"])
                    if "seed" in data:
                        self.spin_seed.setValue(data["seed"])
                    if "model_path" in data:
                        m = data["model_path"]
                        if m not in self.models:
                            self.models.append(m)
                            self.combo_model.addItem(m)
                        self.combo_model.setCurrentText(m)
                    if "output_filename" in data:
                        self.edit_output.setText(data["output_filename"])

                    QMessageBox.information(self, "파일 로드 완료", f"'{os.path.basename(path)}'에서 설정을 성공적으로 불러왔습니다.")
                except Exception as e:
                    QMessageBox.critical(self, "오류", f"파일 파싱 실패: {e}")

        def on_generate(self):
            kwargs = {
                "model_path": self.combo_model.currentText(),
                "prompt": self.txt_prompt.toPlainText().strip(),
                "negative_prompt": self.txt_neg_prompt.toPlainText().strip(),
                "width": self.spin_width.value(),
                "height": self.spin_height.value(),
                "steps": self.spin_steps.value(),
                "guidance_scale": self.spin_scale.value(),
                "seed": self.spin_seed.value(),
                "output_filename": self.edit_output.text().strip() or "output.png"
            }

            self.btn_generate.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.lbl_status.setText("⏳ GPU에서 모델 로드 및 추론 중...")

            self.worker = WorkerThread(kwargs)
            self.worker.finished_signal.connect(self.on_generation_finished)
            self.worker.error_signal.connect(self.on_generation_error)
            self.worker.start()

        def on_generation_finished(self, img_path):
            self.btn_generate.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.btn_open_folder.setEnabled(True)
            self.lbl_status.setText(f"✅ 생성 완료! 저장 경로: {img_path}")

            if os.path.exists(img_path):
                pixmap = QPixmap(img_path)
                scaled_pixmap = pixmap.scaled(self.scroll_area.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.lbl_preview.setPixmap(scaled_pixmap)

        def on_generation_error(self, err_msg):
            self.btn_generate.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_status.setText("❌ 오류 발생!")
            QMessageBox.critical(self, "추론 오류", f"이미지 생성 중 오류가 발생했습니다:\n{err_msg}")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stable Diffusion & FLUX.2 CLI/GUI Generator")
    parser.add_argument("--gui", action="store_true", help="Qt6 그래픽 사용자 인터페이스(GUI) 실행")
    parser.add_argument("-f", "--file", type=str, default=None, help="프롬프트 및 설정 파일 (.md, .txt)")
    parser.add_argument("--model", type=str, default="models/CyberRealistic_FINAL_FP16.safetensors", help="모델 경로")
    parser.add_argument("--prompt", type=str, default=None, help="프롬프트 텍스트")
    parser.add_argument("--negative-prompt", type=str, default=None, help="네거티브 프롬프트")
    parser.add_argument("--width", type=int, default=None, help="이미지 너비")
    parser.add_argument("--height", type=int, default=None, help="이미지 높이")
    parser.add_argument("--steps", type=int, default=None, help="추론 스텝")
    parser.add_argument("--scale", type=float, default=None, help="Guidance Scale")
    parser.add_argument("--seed", type=int, default=None, help="랜덤 시드")
    parser.add_argument("--output", type=str, default=None, help="출력 파일명")

    args = parser.parse_args()

    # 1. GUI 모드
    if args.gui:
        launch_qt6_gui()
        sys.exit(0)

    # 2. 파일 기반 설정 로드
    file_params: Dict[str, Any] = {}
    if args.file:
        print(f"[입력] 설정 파일 읽기: {args.file}")
        file_params = parse_input_file(args.file)

    # 기본 파라미터 조합 (우선순위: CLI 인자 > 파일 설정 > 기본값)
    kwargs = {
        "model_path": args.model if args.model != "models/CyberRealistic_FINAL_FP16.safetensors" or "model_path" not in file_params else file_params["model_path"],
        "prompt": args.prompt or file_params.get("prompt") or (
            "masterpiece, best quality, ultra-detailed, a futuristic cyberpunk laboratory "
            "with holographic displays, glowing neon circuits, cinematic lighting, 8k resolution"
        ),
        "negative_prompt": args.negative_prompt or file_params.get("negative_prompt"),
        "width": args.width or file_params.get("width") or 832,
        "height": args.height or file_params.get("height") or 512,
        "steps": args.steps or file_params.get("steps") or 25,
        "guidance_scale": args.scale or file_params.get("guidance_scale") or 7.5,
        "seed": args.seed if args.seed is not None else file_params.get("seed", 42),
        "output_filename": args.output or file_params.get("output_filename") or "result.png"
    }

    run_generation(**kwargs)
