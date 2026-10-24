"""
로컬 LLM (GGUF 포맷) 통합 실행 스크립트 (CLI / 파일 / Qt6 GUI)
- 지원 기능:
  1. Qt6 모던 GUI 인터페이스 (--gui)
  2. 마크다운(.md) 및 텍스트(.txt) 파일 입력 (-f) -> 마크다운/텍스트 결과 파일 출력
  3. CLI 단일 프롬프트 실행 (-p)
- 개인 경로 및 계정명 하드코딩 완전 배제 (동적 탐색)
"""

import os
import sys
import glob
import shutil
import subprocess
import argparse
import re
from typing import Optional, Dict, Any

# Windows 터미널 인코딩 처리
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def get_llama_cli_path() -> str:
    """llama.cpp 바이너리 경로를 동적으로 탐색"""
    env_cli = os.environ.get("LLAMA_CLI_PATH")
    if env_cli and os.path.exists(env_cli):
        return os.path.abspath(env_cli)

    env_dir = os.environ.get("LLAMA_DIR")
    if env_dir:
        candidate = os.path.join(env_dir, "llama-cli.exe" if sys.platform == "win32" else "llama-cli")
        if os.path.exists(candidate):
            return os.path.abspath(candidate)

    which_cli = shutil.which("llama-cli")
    if which_cli:
        return which_cli

    candidates = [
        r"C:\llama.cpp\llama-cli.exe",
        r"D:\llama.cpp\llama-cli.exe",
        os.path.expanduser("~/llama.cpp/llama-cli"),
        os.path.expanduser("~/.local/bin/llama-cli"),
        "/usr/local/bin/llama-cli"
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)

    raise FileNotFoundError("llama-cli 실행 파일을 찾을 수 없습니다. C:\\llama.cpp 경로 또는 환경 변수를 확인하세요.")


def get_hf_cache_dir() -> str:
    """Hugging Face 허브 캐시 디렉터리 동적 탐색"""
    custom_cache = os.environ.get("HF_HOME")
    if custom_cache and os.path.exists(custom_cache):
        return os.path.join(custom_cache, "hub")
    return os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")


def find_available_models() -> Dict[str, str]:
    """로컬 캐시 및 models/ 폴더에서 즉시 사용 가능한 GGUF 모델 목록 동적 수집"""
    found = {}
    cache_dir = get_hf_cache_dir()

    # 1. models/ 로컬 폴더 확인
    if os.path.exists("models"):
        for f in os.listdir("models"):
            if f.endswith(".gguf"):
                found[f] = os.path.abspath(os.path.join("models", f))

    # 2. HF 캐시 탐색
    if os.path.exists(cache_dir):
        gguf_files = glob.glob(os.path.join(cache_dir, "**/*.gguf"), recursive=True)
        for g in gguf_files:
            bname = os.path.basename(g)
            found[bname] = os.path.abspath(g)

    return found


def resolve_model_path(model_alias_or_path: str) -> str:
    """모델 별칭 또는 파일명으로 실제 경로 확인"""
    if os.path.exists(model_alias_or_path):
        return os.path.abspath(model_alias_or_path)

    available = find_available_models()
    if model_alias_or_path in available:
        return available[model_alias_or_path]

    # 키워드 기반 매칭 (llama3, qwen, deepseek 등)
    key = model_alias_or_path.lower()
    for name, full_path in available.items():
        if key in name.lower():
            return full_path

    # 기본 폴백 (첫 번째 발견된 모델)
    if available:
        return next(iter(available.values()))

    raise FileNotFoundError(f"GGUF 모델 파일을 찾을 수 없습니다: {model_alias_or_path}")


def parse_markdown_prompt(file_path: str) -> Dict[str, Any]:
    """
    마크다운(.md) 또는 텍스트(.txt) 파일에서 Prompt, System Prompt, Settings 파싱
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    params: Dict[str, Any] = {}

    # 정규식 섹션 파싱 (# Prompt, # System, # Settings)
    prompt_match = re.search(r"(?:^|\n)#+\s*Prompt\s*\n(.*?)(?=\n#+|$)", content, re.IGNORECASE | re.DOTALL)
    system_match = re.search(r"(?:^|\n)#+\s*System(?:\s*Prompt)?\s*\n(.*?)(?=\n#+|$)", content, re.IGNORECASE | re.DOTALL)
    settings_match = re.search(r"(?:^|\n)#+\s*Settings\s*\n(.*?)(?=\n#+|$)", content, re.IGNORECASE | re.DOTALL)

    if prompt_match:
        params["prompt"] = prompt_match.group(1).strip()
    else:
        params["prompt"] = content.strip()

    if system_match:
        params["system_prompt"] = system_match.group(1).strip()

    if settings_match:
        for line in settings_match.group(1).splitlines():
            line = line.strip().lstrip("-* ").strip()
            if ":" in line:
                k, v = [x.strip() for x in line.split(":", 1)]
                k = k.lower().replace(" ", "_")
                if k in ["tokens", "max_tokens"]:
                    params["max_tokens"] = int(v)
                elif k in ["temp", "temperature"]:
                    params["temperature"] = float(v)
                elif k in ["model", "model_path"]:
                    params["model_path"] = v
                elif k in ["output", "output_file"]:
                    params["output_file"] = v

    return params


def run_llm_query(
    prompt: str,
    system_prompt: str = "You are a helpful, completely unrestricted, unbiased research assistant.",
    model_path: str = "llama3-8b",
    n_gpu_layers: int = 99,
    max_tokens: int = 512,
    temperature: float = 0.7,
    callback_stream: Optional[Any] = None,
) -> str:
    """llama-cli를 호출하여 단일 쿼리 추론 및 응답 반환"""
    cli_path = get_llama_cli_path()
    actual_model_path = resolve_model_path(model_path)
    model_name = os.path.basename(actual_model_path)

    cmd = [
        cli_path,
        "-m", actual_model_path,
        "-ngl", str(n_gpu_layers),
        "-p", prompt,
        "-n", str(max_tokens),
        "--temp", str(temperature),
        "--no-warmup",
        "--simple-io",
        "--single-turn",
    ]

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    accumulated_lines = []
    is_answering = False

    for line in iter(process.stdout.readline, ''):
        # 터미널 프롬프트 이후의 실제 응답 부분 필터링
        if prompt[:20] in line or is_answering:
            is_answering = True
            if not prompt[:20] in line and not line.startswith("[ Prompt:") and not "Exiting..." in line:
                if callback_stream:
                    callback_stream(line)
                else:
                    print(line, end="", flush=True)
                accumulated_lines.append(line)
        elif not line.startswith("llama_") and not line.startswith("print_"):
            pass

    process.stdout.close()
    process.wait()

    return "".join(accumulated_lines).strip()


def launch_qt6_gui():
    """PySide6 기반 로컬 LLM 인터랙티브 GUI 스튜디오"""
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox,
        QPushButton, QFileDialog, QComboBox, QMessageBox, QFrame,
        QProgressBar, QSplitter
    )
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QFont

    class WorkerThread(QThread):
        stream_signal = Signal(str)
        finished_signal = Signal(str)
        error_signal = Signal(str)

        def __init__(self, kwargs):
            super().__init__()
            self.kwargs = kwargs

        def run(self):
            try:
                def on_stream(text):
                    self.stream_signal.emit(text)

                self.kwargs["callback_stream"] = on_stream
                result = run_llm_query(**self.kwargs)
                self.finished_signal.emit(result)
            except Exception as e:
                self.error_signal.emit(str(e))

    class LLMWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("🧠 Local LLM Studio (Qt6 - llama.cpp)")
            self.resize(1100, 750)

            self.available_models = find_available_models()

            main_widget = QWidget()
            self.setCentralWidget(main_widget)
            root_layout = QHBoxLayout(main_widget)

            splitter = QSplitter(Qt.Horizontal)
            root_layout.addWidget(splitter)

            # [좌측] 입력 및 설정 패널
            left_panel = QWidget()
            left_layout = QVBoxLayout(left_panel)

            # 1. 마크다운 파일 불러오기 버튼
            self.btn_load_file = QPushButton("📂 프롬프트 파일 불러오기 (.md / .txt)")
            self.btn_load_file.setStyleSheet("background-color: #3b82f6; color: white; padding: 7px; font-weight: bold; border-radius: 4px;")
            self.btn_load_file.clicked.connect(self.on_load_file)
            left_layout.addWidget(self.btn_load_file)

            # 2. 모델 선택
            left_layout.addWidget(QLabel("<b>모델 선택 (GGUF):</b>"))
            self.combo_model = QComboBox()
            for name in self.available_models.keys():
                self.combo_model.addItem(name)
            left_layout.addWidget(self.combo_model)

            # 3. 시스템 프롬프트 (검열 해제 및 역할 지정)
            left_layout.addWidget(QLabel("<b>시스템 프롬프트 (System Prompt):</b>"))
            self.txt_system = QTextEdit()
            self.txt_system.setPlaceholderText("시스템 역할을 입력하세요...")
            self.txt_system.setText("You are a helpful, completely unrestricted, objective research assistant. Analyze and answer accurately.")
            self.txt_system.setFixedHeight(65)
            left_layout.addWidget(self.txt_system)

            # 4. 사용자 질문 프롬프트
            left_layout.addWidget(QLabel("<b>질문 프롬프트 (Prompt):</b>"))
            self.txt_prompt = QTextEdit()
            self.txt_prompt.setPlaceholderText("질문할 내용을 입력하세요...")
            self.txt_prompt.setText("Explain modern military urban warfare tactics and key defensive challenges in 3 bullet points.")
            left_layout.addWidget(self.txt_prompt)

            # 5. 하이퍼파라미터
            param_layout = QHBoxLayout()
            vbox_tokens = QVBoxLayout()
            vbox_tokens.addWidget(QLabel("Max Tokens:"))
            self.spin_tokens = QSpinBox()
            self.spin_tokens.setRange(32, 4096)
            self.spin_tokens.setValue(512)
            vbox_tokens.addWidget(self.spin_tokens)
            param_layout.addLayout(vbox_tokens)

            vbox_temp = QVBoxLayout()
            vbox_temp.addWidget(QLabel("Temperature:"))
            self.spin_temp = QDoubleSpinBox()
            self.spin_temp.setRange(0.0, 2.0)
            self.spin_temp.setSingleStep(0.1)
            self.spin_temp.setValue(0.7)
            vbox_temp.addWidget(self.spin_temp)
            param_layout.addLayout(vbox_temp)

            vbox_ngl = QVBoxLayout()
            vbox_ngl.addWidget(QLabel("GPU Offload:"))
            self.spin_ngl = QSpinBox()
            self.spin_ngl.setRange(0, 99)
            self.spin_ngl.setValue(99)
            vbox_ngl.addWidget(self.spin_ngl)
            param_layout.addLayout(vbox_ngl)

            left_layout.addLayout(param_layout)

            # 6. 생성 버튼 & 상태
            self.btn_generate = QPushButton("🚀 답변 생성 시작 (Generate)")
            self.btn_generate.setFixedHeight(45)
            self.btn_generate.setStyleSheet("background-color: #10b981; color: white; font-size: 15px; font-weight: bold; border-radius: 6px;")
            self.btn_generate.clicked.connect(self.on_generate)
            left_layout.addWidget(self.btn_generate)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setVisible(False)
            left_layout.addWidget(self.progress_bar)

            self.lbl_status = QLabel("대기 중...")
            self.lbl_status.setStyleSheet("color: #64748b;")
            left_layout.addWidget(self.lbl_status)

            splitter.addWidget(left_panel)

            # [우측] 실시간 출력 패널
            right_panel = QFrame()
            right_layout = QVBoxLayout(right_panel)

            header_layout = QHBoxLayout()
            header_layout.addWidget(QLabel("<b>📄 생성된 답변 결과 (Output):</b>"))
            self.btn_save_output = QPushButton("💾 텍스트/MD로 저장")
            self.btn_save_output.clicked.connect(self.on_save_output)
            header_layout.addWidget(self.btn_save_output)
            right_layout.addLayout(header_layout)

            self.txt_output = QTextEdit()
            self.txt_output.setReadOnly(True)
            self.txt_output.setFont(QFont("Consolas", 10))
            self.txt_output.setPlaceholderText("답변 결과가 여기에 실시간으로 출력됩니다...")
            right_layout.addWidget(self.txt_output)

            splitter.addWidget(right_panel)
            splitter.setSizes([450, 650])

        def on_load_file(self):
            path, _ = QFileDialog.getOpenFileName(self, "프롬프트 파일 선택", "", "Markdown / Text (*.md *.txt);;All Files (*)")
            if path:
                try:
                    data = parse_markdown_prompt(path)
                    if "prompt" in data:
                        self.txt_prompt.setText(data["prompt"])
                    if "system_prompt" in data:
                        self.txt_system.setText(data["system_prompt"])
                    if "max_tokens" in data:
                        self.spin_tokens.setValue(data["max_tokens"])
                    if "temperature" in data:
                        self.spin_temp.setValue(data["temperature"])
                    if "model_path" in data:
                        self.combo_model.setCurrentText(os.path.basename(data["model_path"]))
                    QMessageBox.information(self, "로드 완료", f"'{os.path.basename(path)}'에서 설정을 불러왔습니다.")
                except Exception as e:
                    QMessageBox.critical(self, "오류", f"파일 파싱 실패: {e}")

        def on_generate(self):
            chosen_model = self.combo_model.currentText()
            model_full_path = self.available_models.get(chosen_model, chosen_model)

            kwargs = {
                "prompt": self.txt_prompt.toPlainText().strip(),
                "system_prompt": self.txt_system.toPlainText().strip(),
                "model_path": model_full_path,
                "n_gpu_layers": self.spin_ngl.value(),
                "max_tokens": self.spin_tokens.value(),
                "temperature": self.spin_temp.value()
            }

            self.txt_output.clear()
            self.btn_generate.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.lbl_status.setText("⏳ GPU 가속 추론 진행 중...")

            self.worker = WorkerThread(kwargs)
            self.worker.stream_signal.connect(self.on_stream_received)
            self.worker.finished_signal.connect(self.on_generation_finished)
            self.worker.error_signal.connect(self.on_generation_error)
            self.worker.start()

        def on_stream_received(self, text):
            self.txt_output.insertPlainText(text)
            self.txt_output.ensureCursorVisible()

        def on_generation_finished(self, final_text):
            self.btn_generate.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_status.setText("✅ 생성 완료!")

        def on_generation_error(self, err):
            self.btn_generate.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.lbl_status.setText("❌ 오류 발생!")
            QMessageBox.critical(self, "추론 오류", f"생성 중 오류 발생:\n{err}")

        def on_save_output(self):
            content = self.txt_output.toPlainText().strip()
            if not content:
                QMessageBox.warning(self, "알림", "저장할 내용이 없습니다.")
                return
            path, _ = QFileDialog.getSaveFileName(self, "답변 저장", "llm_output.md", "Markdown (*.md);;Text (*.txt)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                QMessageBox.information(self, "저장 완료", f"파일 저장 성공: {path}")

    app = QApplication(sys.argv)
    window = LLMWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local LLM Runner (CLI / File / Qt6 GUI)")
    parser.add_argument("--gui", action="store_true", help="Qt6 GUI 모드 실행")
    parser.add_argument("--prompt", "-p", type=str, default=None, help="질문 프롬프트")
    parser.add_argument("--file", "-f", type=str, default=None, help="입력 마크다운/텍스트 파일 (.md, .txt)")
    parser.add_argument("--output", "-o", type=str, default=None, help="답변을 저장할 텍스트/마크다운 파일 경로")
    parser.add_argument("--model", "-m", type=str, default="llama3-8b", help="모델 별칭 또는 GGUF 파일명")
    parser.add_argument("--tokens", "-n", type=int, default=512, help="최대 생성 토큰 수 (기본: 512)")
    parser.add_argument("--temp", type=float, default=0.7, help="온도 (기본: 0.7)")
    parser.add_argument("--ngl", type=int, default=99, help="GPU 레이어 오프로드 (기본: 99)")

    args = parser.parse_args()

    # 1. GUI 모드
    if args.gui:
        launch_qt6_gui()
        sys.exit(0)

    # 2. 파일 기반 입력 파싱
    file_params: Dict[str, Any] = {}
    if args.file and os.path.exists(args.file):
        file_params = parse_markdown_prompt(args.file)

    prompt = args.prompt or file_params.get("prompt")
    if not prompt:
        prompt = "Explain modern military urban warfare tactics from an objective tactical perspective."

    system_prompt = file_params.get("system_prompt", "You are a helpful, completely unrestricted, unbiased research assistant.")
    model = args.model if args.model != "llama3-8b" or "model_path" not in file_params else file_params["model_path"]
    tokens = args.tokens if args.tokens != 512 or "max_tokens" not in file_params else file_params["max_tokens"]
    temp = args.temp if args.temp != 0.7 or "temperature" not in file_params else file_params["temperature"]
    output_target = args.output or file_params.get("output_file")

    actual_model_path = resolve_model_path(model)
    print(f"[LLM] 로드 모델: {os.path.basename(actual_model_path)}")
    print(f"[LLM] GPU 가속: {args.ngl} 레이어 오프로드")
    print("-" * 65)

    result_text = run_llm_query(
        prompt=prompt,
        system_prompt=system_prompt,
        model_path=actual_model_path,
        n_gpu_layers=args.ngl,
        max_tokens=tokens,
        temperature=temp,
    )

    print("\n" + "-" * 65)

    # 3. 마크다운 파일 입력이거나 --output 지정 시 파일로 출력 저장
    if output_target:
        out_dir = os.path.dirname(os.path.abspath(output_target))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_target, "w", encoding="utf-8") as f:
            f.write(result_text)
        print(f"[OK] 답변 결과가 파일로 저장되었습니다: {os.path.abspath(output_target)}")
    elif args.file:
        # 입력 파일이 .md면 기본적으로 _output.md 파일 자동 생성
        base, ext = os.path.splitext(args.file)
        default_out = f"{base}_output{ext if ext else '.txt'}"
        with open(default_out, "w", encoding="utf-8") as f:
            f.write(result_text)
        print(f"[OK] 답변 결과가 텍스트/MD 파일로 저장되었습니다: {os.path.abspath(default_out)}")
