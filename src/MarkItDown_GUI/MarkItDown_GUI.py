# -*- coding: utf-8 -*-
"""
MarkItDown GUI - Microsoft MarkItDown 기반 문서 변환 및 지능형 요약 프로그램
GUI 프레임워크: PySide6 (LGPL v3 - 상용 및 비공개 배포 안전) / PyQt6 호환
지원 형식: docx, hwp, hwpx, xlsx, pptx, txt, pdf, html, csv, json, xml 등 -> md (Markdown)
"""

import sys
import os
import re
import math
import time
import zlib
import struct
import zipfile
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# ==========================================
# GUI 바인딩 (PySide6 우선 적용 - LGPL v3 라이선스)
# ==========================================
try:
    from PySide6.QtCore import Qt, QThread, Signal as pyqtSignal, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDesktopServices
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
        QProgressBar, QTextEdit, QGroupBox, QCheckBox, QFrame
    )
    QT_BACKEND = "PySide6 (LGPL v3)"
except ImportError:
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
    from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QDesktopServices
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
        QProgressBar, QTextEdit, QGroupBox, QCheckBox, QFrame
    )
    QT_BACKEND = "PyQt6 (GPL v3)"

# OLE 구조 파싱 (HWP 5.0)
try:
    import olefile
    OLEFILE_AVAILABLE = True
except ImportError:
    OLEFILE_AVAILABLE = False

# Microsoft MarkItDown
try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False


# ==============================================================================
# 1. HWP (한글 5.0 바이너리) 파서 - 제어 바이트 정밀 스킵 및 글자 깨짐 방지
# ==============================================================================
def parse_hwp_para_text(record_data: bytes) -> str:
    """
    HWPTAG_PARA_TEXT(67) 레코드 바이트에서 UTF-16LE 텍스트를 정밀 디코딩합니다.
    HWP 5.0 명세에 따라 확장 제어 문자(표, 개체, 머리말 등)에 수반되는
    16바이트(8글자) 추가 파라미터 바이트를 스킵하여 외계어/깨진 글자 출현을 방지합니다.
    """
    chars = []
    i = 0
    total_bytes = len(record_data)

    # 16바이트 추가 파라미터를 갖는 확장 컨트롤 코드 목록
    # 1: 구역/단, 2: 필드시작, 3: 필드끝, 11: 표/그림, 12: 글자겹침, 14: 바탕쪽, 15: 숨은설명,
    # 16: 머리말/꼬리말, 17: 각주/미주, 18: 자동번호, 21: 페이지컨트롤, 22: 책갈피, 23: 덧말
    EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}

    while i + 1 < total_bytes:
        code = struct.unpack("<H", record_data[i:i + 2])[0]
        i += 2

        # 확장 컨트롤: 뒤따르는 16바이트(UTF-16 8글자) 제어 파라미터 스킵
        if code in EXTENDED_CONTROLS:
            i += 16
            continue
        elif code == 9:  # Tab
            chars.append("    ")
        elif code in (10, 13):  # 줄바꿈 / 문단 끝
            chars.append("\n")
        elif code in (24, 30, 31):  # 하이픈, 묶음 빈칸, 고정폭 빈칸
            chars.append(" ")
        elif code < 32:  # 기타 0~31 범위의 미지원 제어 문자 스킵
            continue
        elif 0xE000 <= code <= 0xF8FF:  # HWP 전용 PUA(Private Use Area) 특수 한자/글머리 기호 스킵
            continue
        else:
            chars.append(chr(code))

    text = "".join(chars)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_hwp_to_markdown(file_path: str) -> str:
    """
    한글 HWP(바이너리 5.0) 파일에서 본문 텍스트를 추출하여 깨끗한 Markdown으로 변환합니다.
    """
    if not OLEFILE_AVAILABLE:
        raise RuntimeError("hwp 파일을 처리하려면 olefile 라이브러리가 필요합니다. pip install olefile을 실행하세요.")

    if not olefile.isOleFile(file_path):
        raise ValueError("올바른 HWP 파일 형식이 아닙니다 (OLE Compound 구조 아님).")

    with olefile.OleFileIO(file_path) as ole:
        # 1. FileHeader 읽기 및 압축 여부 확인
        header_data = ole.openstream("FileHeader").read()
        if len(header_data) < 40:
            raise ValueError("HWP 헤더 정보가 올바르지 않습니다.")
        is_compressed = (header_data[36] & 1) == 1

        # 2. Section 목록 탐색 (BodyText/Section0, Section1, ...)
        dirs = ole.listdir()
        sections = []
        for d in dirs:
            if len(d) == 2 and d[0] == "BodyText" and d[1].startswith("Section"):
                sections.append(d)

        if not sections:
            raise ValueError("HWP 문서 내 본문 섹션(BodyText/Section)을 찾을 수 없습니다.")

        # 섹션 번호 순으로 정렬
        def get_sec_num(item):
            sec_name = item[1].replace("Section", "")
            return int(sec_name) if sec_name.isdigit() else 9999

        sections.sort(key=get_sec_num)

        paragraphs = []
        for sec in sections:
            stream = ole.openstream(sec)
            raw_data = stream.read()

            # 압축 해제
            if is_compressed:
                try:
                    data = zlib.decompress(raw_data, -15)
                except Exception:
                    try:
                        data = zlib.decompress(raw_data)
                    except Exception as e:
                        paragraphs.append(f"> [경고] {sec[1]} 압축 해제 오류: {e}")
                        continue
            else:
                data = raw_data

            # 3. 레코드 파싱
            offset = 0
            total_len = len(data)
            while offset < total_len:
                if offset + 4 > total_len:
                    break
                header = struct.unpack("<I", data[offset:offset + 4])[0]
                tag_id = header & 0x3FF
                size = (header >> 20) & 0xFFF
                offset += 4

                # 확장 크기(DWORD) 처리
                if size == 0xFFF:
                    if offset + 4 > total_len:
                        break
                    size = struct.unpack("<I", data[offset:offset + 4])[0]
                    offset += 4

                if offset + size > total_len:
                    break

                record_data = data[offset:offset + size]
                offset += size

                # HWPTAG_PARA_TEXT = 67 (0x43)
                if tag_id == 67:
                    try:
                        para_text = parse_hwp_para_text(record_data)
                        if para_text:
                            paragraphs.append(para_text)
                    except Exception:
                        pass

    result = "\n\n".join(paragraphs).strip()
    return result if result else "(HWP 문서 내용이 비어 있거나 텍스트를 추출할 수 없습니다.)"


# ==============================================================================
# 2. HWPX (한글 OWPML) 파서
# ==============================================================================
def extract_hwpx_to_markdown(file_path: str) -> str:
    """
    한글 OWPML(HWPX) 파일에서 본문 문단 및 표를 추출하여 Markdown 형식으로 변환합니다.
    """
    lines = []
    with zipfile.ZipFile(file_path, "r") as zf:
        section_names = sorted(
            [name for name in zf.namelist() if name.startswith("Contents/section") and name.endswith(".xml")]
        )
        if not section_names:
            section_names = sorted(
                [name for name in zf.namelist() if "section" in name.lower() and name.endswith(".xml")]
            )

        for sec_name in section_names:
            try:
                xml_content = zf.read(sec_name)
                root = ET.fromstring(xml_content)

                # 표(tbl) 태그 내부에 있는 p 요소들을 수집하여 본문과의 중복 출력 방지
                table_p_elements = set()
                for tbl in root.findall(".//{*}tbl"):
                    for p in tbl.findall(".//{*}p"):
                        table_p_elements.add(p)

                for elem in root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

                    # 1. 표(tbl) -> 마크다운 테이블 생성
                    if tag == "tbl":
                        table_rows = []
                        for tr in elem.findall(".//{*}tr"):
                            row_cells = []
                            for tc in tr.findall(".//{*}tc"):
                                cell_texts = []
                                for p in tc.findall(".//{*}p"):
                                    t = "".join(p.itertext()).strip()
                                    if t:
                                        cell_texts.append(t)
                                cell_str = " ".join(cell_texts) if cell_texts else "".join(tc.itertext()).strip()
                                cell_str = cell_str.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")
                                row_cells.append(cell_str)
                            if row_cells:
                                table_rows.append(row_cells)

                        if table_rows:
                            max_cols = max(len(r) for r in table_rows)
                            if max_cols > 0:
                                norm_rows = [r + [""] * (max_cols - len(r)) for r in table_rows]
                                table_block = [
                                    "| " + " | ".join(norm_rows[0]) + " |",
                                    "| " + " | ".join(["---"] * max_cols) + " |"
                                ]
                                for row in norm_rows[1:]:
                                    table_block.append("| " + " | ".join(row) + " |")
                                lines.append("\n".join(table_block))

                    # 2. 본문 문단(p) -> 텍스트 추출
                    elif tag == "p":
                        if elem in table_p_elements:
                            continue
                        text = "".join(elem.itertext()).strip()
                        if text:
                            lines.append(text)
            except Exception as e:
                lines.append(f"> [경고] 섹션 {sec_name} 파싱 중 오류: {e}")

    result = "\n\n".join(lines).strip()
    return result if result else "(HWPX 문서 내용이 비어 있거나 텍스트를 추출할 수 없습니다.)"


# ==============================================================================
# 3. 고품질 지능형 한국어/영문 문서 요약 엔진 (TF-ISF + 위치 가중치 + 중복 방지)
# ==============================================================================
KOREAN_STOPWORDS = {
    "있는", "있으며", "있습니다", "있다", "하는", "하며", "합니다", "한다",
    "대한", "대해", "위해", "통해", "의해", "따라", "따른", "관한", "관련",
    "경우", "모든", "어떤", "이러한", "그러한", "저러한", "등을", "등의",
    "이를", "이에", "따라서", "또한", "그리고", "그러나", "하지만", "또는",
    "모두", "각각", "현재", "주요", "내용", "결과", "사항", "기준", "방법",
    "대상", "목적", "개요", "분야", "이하", "이상", "것으로", "됩니다", "되고",
    "사업", "계획", "추진", "보고", "제출", "작성", "다음", "아래", "위의",
    "하여", "하며", "하도록", "등이", "등에", "대하여", "위하여", "있음", "없음"
}


def is_meaningful_sentence(s: str) -> bool:
    """
    단순 기호, 머리말, 날짜, 목차, 표 파편 등 무의미한 문장을 걸러내고
    완결성 있는 정보 문장만을 추출합니다.
    """
    s = s.strip()
    if len(s) < 25 or len(s) > 280:
        return False

    if s.startswith("|") or s.startswith("#") or s.startswith("http") or s.startswith("!"):
        return False

    specials = len(re.findall(r"[^가-힣a-zA-Z0-9\s.,'\"()%·-]", s))
    if specials / len(s) > 0.25:
        return False

    hangul_count = len(re.findall(r"[가-힣]", s))
    if hangul_count < 8:
        english_words = re.findall(r"[a-zA-Z]{3,}", s)
        if len(english_words) < 5:
            return False

    if not re.search(r"([가-힣a-zA-Z0-9][.!?]?|[다함음요까임됨])$", s):
        return False

    return True


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """두 문장 단어 세트 간의 자카드 유사도를 계산하여 중복 문장을 방지합니다."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def generate_document_summary(text: str, max_sentences: int = 4) -> str:
    """
    위치 가중치(서론/결론 강조), 단어 중요도(TF-ISF), 문장 길이 최적화,
    중복 제거(MMR)를 결합하여 고품질의 핵심 요약을 생성합니다.
    """
    # 1. 문장 분리
    raw_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text)
        if s.strip()
    ]

    # 2. 유효 문장 필터링
    valid_sentences = []
    for s in raw_sentences:
        clean_s = re.sub(r"\s+", " ", s).strip()
        if is_meaningful_sentence(clean_s):
            valid_sentences.append(clean_s)

    if not valid_sentences:
        valid_sentences = [s for s in raw_sentences if len(s) >= 20 and not s.startswith("|")][:max_sentences]

    if not valid_sentences:
        return ""

    if len(valid_sentences) <= max_sentences:
        bullet_list = "\n".join([f"- {s}" for s in valid_sentences])
        return (
            "> [!NOTE]\n"
            "> ### 📌 문서 핵심 요약 (Summary)\n"
            ">\n" +
            "\n".join([f"> {b}" for b in bullet_list.splitlines()]) +
            "\n\n---\n"
        )

    # 3. 단어 빈도(TF) 및 역문장 빈도(ISF) 분석
    sentence_words = []
    all_words = []
    for s in valid_sentences:
        words = [
            w for w in re.findall(r"[가-힣a-zA-Z]{2,}", s.lower())
            if w not in KOREAN_STOPWORDS
        ]
        sentence_words.append(words)
        all_words.extend(words)

    word_freq = Counter(all_words)
    total_valid = len(valid_sentences)

    word_isf = {}
    for word in word_freq:
        doc_count = sum(1 for words in sentence_words if word in words)
        word_isf[word] = math.log((total_valid + 1) / (doc_count + 1)) + 1.0

    # 4. 문장별 다면 점수 산출
    scored_sentences = []
    for idx, (sentence, words) in enumerate(zip(valid_sentences, sentence_words)):
        if not words:
            continue

        tf_isf_score = sum(word_freq[w] * word_isf.get(w, 1.0) for w in words) / (len(words) ** 0.6)

        # 위치 가중치: 서론(첫 25%)은 1.6배, 결론(끝 25%)은 1.3배 가중
        rel_pos = idx / total_valid
        if rel_pos <= 0.25:
            pos_weight = 1.6
        elif rel_pos >= 0.75:
            pos_weight = 1.3
        else:
            pos_weight = 1.0

        # 길이 최적화 가중치: 45자 ~ 140자 문장이 가장 가독성 높음
        s_len = len(sentence)
        if 45 <= s_len <= 140:
            len_weight = 1.2
        elif s_len < 30 or s_len > 220:
            len_weight = 0.8
        else:
            len_weight = 1.0

        final_score = tf_isf_score * pos_weight * len_weight
        scored_sentences.append({
            "idx": idx,
            "score": final_score,
            "text": sentence,
            "words": set(words)
        })

    if not scored_sentences:
        return ""

    scored_sentences.sort(key=lambda x: x["score"], reverse=True)

    # 5. 다양성 확보 및 중복 제거
    selected = []
    for cand in scored_sentences:
        if len(selected) >= max_sentences:
            break

        is_redundant = False
        for s in selected:
            if jaccard_similarity(cand["words"], s["words"]) > 0.45:
                is_redundant = True
                break

        if not is_redundant:
            selected.append(cand)

    selected.sort(key=lambda x: x["idx"])

    bullet_lines = "\n".join([f"- {item['text']}" for item in selected])
    summary_block = (
        "> [!NOTE]\n"
        "> ### 📌 문서 핵심 요약 (Summary)\n"
        ">\n" +
        "\n".join([f"> {line}" for line in bullet_lines.splitlines()]) +
        "\n\n---\n"
    )
    return summary_block


# ==============================================================================
# 4. 백그라운드 변환 워커 스레드
# ==============================================================================
class ConversionWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, str, float)

    def __init__(self, input_path: str, output_path: str, include_summary: bool = True):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.include_summary = include_summary

    def run(self):
        start_time = time.time()
        try:
            self.progress.emit(10, "파일 확인 중...")
            inp = Path(self.input_path)
            out = Path(self.output_path)

            if not inp.exists():
                raise FileNotFoundError(f"입력 파일이 존재하지 않습니다: {self.input_path}")

            out.parent.mkdir(parents=True, exist_ok=True)

            ext = inp.suffix.lower()
            md_content = ""

            self.progress.emit(30, f"[{ext.upper()}] 정밀 파싱 진행 중...")

            # 1. HWP (한글 바이너리 5.0) - 제어 바이트 필터링 적용
            if ext == ".hwp":
                self.progress.emit(45, "HWP 바이너리 레코드 정밀 분석 및 글자 정제 중...")
                md_content = extract_hwp_to_markdown(str(inp))

            # 2. HWPX (한글 OWPML) 문서 처리
            elif ext == ".hwpx":
                self.progress.emit(45, "HWPX(한글 OWPML) 문서 파싱 중...")
                md_content = extract_hwpx_to_markdown(str(inp))

            # 3. 일반 텍스트 문서 (.txt, .log 등)
            elif ext in [".txt", ".log", ".ini", ".cfg"]:
                self.progress.emit(50, "텍스트 파일 인코딩 분석 및 변환 중...")
                text = None
                for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin1"]:
                    try:
                        with open(inp, "r", encoding=enc) as f:
                            text = f.read()
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                if text is None:
                    with open(inp, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                md_content = text

            # 4. Microsoft MarkItDown 기본 지원 포맷 (docx, xlsx, pptx, pdf, html 등)
            else:
                if not MARKITDOWN_AVAILABLE:
                    raise RuntimeError("microsoft markitdown 라이브러리가 설치되지 않았습니다. pip install markitdown을 실행하세요.")
                
                self.progress.emit(40, f"MarkItDown 엔진으로 {ext.upper()} 변환 중...")
                md_engine = MarkItDown()
                result = md_engine.convert(str(inp))
                md_content = result.text_content or ""

            # 요약 옵션 적용
            if self.include_summary and md_content:
                self.progress.emit(75, "문서 핵심 내용 지능형 요약(TF-ISF + 문맥 분석) 생성 중...")
                summary_header = generate_document_summary(md_content, max_sentences=4)
                if summary_header:
                    md_content = f"# {inp.stem}\n\n" + summary_header + "\n" + md_content

            self.progress.emit(90, "Markdown 파일 저장 중...")
            with open(out, "w", encoding="utf-8") as f:
                f.write(md_content)

            elapsed = round(time.time() - start_time, 2)
            self.progress.emit(100, f"변환 완료! (소요 시간: {elapsed}초)")
            self.finished.emit(True, md_content, str(out), elapsed)

        except Exception as e:
            elapsed = round(time.time() - start_time, 2)
            self.progress.emit(0, "오류 발생")
            self.finished.emit(False, str(e), "", elapsed)


# ==============================================================================
# 5. 메인 GUI 윈도우
# ==============================================================================
class MarkItDownGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"MarkItDown GUI - 문서 마크다운 변환기 [{QT_BACKEND}]")
        self.resize(860, 740)
        self.setMinimumSize(720, 560)
        self.setAcceptDrops(True)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # 1. 헤더 섹션
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(6)

        title_label = QLabel("📄 Microsoft MarkItDown 변환기")
        title_label.setObjectName("titleLabel")
        desc_label = QLabel("다양한 문서(DOCX, HWP, HWPX, XLSX, PPTX, PDF, TXT 등)를 깨끗한 Markdown(.md) 파일로 변환 및 정밀 요약합니다.")
        desc_label.setObjectName("descLabel")

        header_layout.addWidget(title_label)
        header_layout.addWidget(desc_label)
        main_layout.addWidget(header_frame)

        # 2. 파일 경로 설정 그룹
        io_group = QGroupBox("파일 경로 설정")
        io_group.setObjectName("ioGroup")
        io_layout = QVBoxLayout(io_group)
        io_layout.setSpacing(12)

        # (1) 입력 파일
        input_label = QLabel("📥 입력 파일 (경로 + 파일명):")
        input_label.setStyleSheet("font-weight: bold;")
        input_h_layout = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("변환할 파일을 선택하거나 여기에 드래그 앤 드롭하세요. (docx, hwp, hwpx, xlsx, pptx, pdf, txt 등)")
        self.input_edit.textChanged.connect(self.on_input_text_changed)

        self.btn_browse_input = QPushButton("파일 선택...")
        self.btn_browse_input.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_input.clicked.connect(self.browse_input_file)

        input_h_layout.addWidget(self.input_edit)
        input_h_layout.addWidget(self.btn_browse_input)

        io_layout.addWidget(input_label)
        io_layout.addLayout(input_h_layout)

        # (2) 출력 파일
        output_label = QLabel("📤 출력 파일 (경로 + 파일명):")
        output_label.setStyleSheet("font-weight: bold;")
        output_h_layout = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("저장될 마크다운 파일 경로 (*.md)")

        self.btn_browse_output = QPushButton("저장 위치 변경...")
        self.btn_browse_output.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse_output.clicked.connect(self.browse_output_file)

        output_h_layout.addWidget(self.output_edit)
        output_h_layout.addWidget(self.btn_browse_output)

        io_layout.addWidget(output_label)
        io_layout.addLayout(output_h_layout)

        main_layout.addWidget(io_group)

        # 3. 옵션 체크박스
        opt_layout = QHBoxLayout()
        self.chk_summary = QCheckBox("문서 상단에 핵심 요약(Summary) 추가")
        self.chk_summary.setChecked(True)
        self.chk_open_folder = QCheckBox("변환 완료 후 대상 폴더 열기")
        self.chk_open_folder.setChecked(False)
        self.chk_preview = QCheckBox("변환 내용 미리보기")
        self.chk_preview.setChecked(True)

        opt_layout.addWidget(self.chk_summary)
        opt_layout.addWidget(self.chk_open_folder)
        opt_layout.addWidget(self.chk_preview)
        opt_layout.addStretch()
        main_layout.addLayout(opt_layout)

        # 4. 액션 버튼 (작업시작, 프로그램 종료)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_start = QPushButton("🚀 작업시작")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setFixedHeight(42)
        self.btn_start.clicked.connect(self.start_conversion)

        self.btn_exit = QPushButton("❌ 프로그램 종료")
        self.btn_exit.setObjectName("btnExit")
        self.btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_exit.setFixedHeight(42)
        self.btn_exit.clicked.connect(self.close)

        btn_layout.addWidget(self.btn_start, stretch=3)
        btn_layout.addWidget(self.btn_exit, stretch=1)
        main_layout.addLayout(btn_layout)

        # 5. 진행 상태 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(18)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel(f"상태: 변환할 파일을 지정하고 [작업시작]을 누르세요. ({QT_BACKEND})")
        self.status_label.setObjectName("statusLabel")
        main_layout.addWidget(self.status_label)

        # 6. 미리보기 영역
        preview_group = QGroupBox("변환 결과 미리보기 (Markdown)")
        preview_group.setObjectName("previewGroup")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("변환이 완료되면 이곳에 마크다운 텍스트가 표시됩니다.")
        preview_layout.addWidget(self.preview_edit)

        # 미리보기 보조 버튼 (복사, 파일 열기, 폴더 열기)
        preview_btn_layout = QHBoxLayout()
        self.btn_copy = QPushButton("📋 마크다운 복사")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self.copy_preview_to_clipboard)

        self.btn_open_file = QPushButton("📄 마크다운 파일 열기")
        self.btn_open_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_file.clicked.connect(self.open_generated_file)

        self.btn_open_dir = QPushButton("📁 저장 폴더 열기")
        self.btn_open_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_dir.clicked.connect(self.open_target_folder)

        preview_btn_layout.addWidget(self.btn_copy)
        preview_btn_layout.addWidget(self.btn_open_file)
        preview_btn_layout.addWidget(self.btn_open_dir)
        preview_btn_layout.addStretch()

        preview_layout.addLayout(preview_btn_layout)
        main_layout.addWidget(preview_group, stretch=1)

        self.apply_styles()

    def apply_styles(self):
        style = """
        QWidget {
            font-family: "Segoe UI", "맑은 고딕", "Malgun Gothic", sans-serif;
            font-size: 13px;
            color: #2b2b2b;
        }
        #headerFrame {
            background-color: #f0f4f9;
            border: 1px solid #d2e3fc;
            border-radius: 8px;
        }
        #titleLabel {
            font-size: 18px;
            font-weight: bold;
            color: #1a73e8;
        }
        #descLabel {
            font-size: 12px;
            color: #5f6368;
        }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #dcdfe6;
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 14px;
            background-color: #fafbfc;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 4px;
            color: #303133;
        }
        QLineEdit {
            border: 1px solid #c0c4cc;
            border-radius: 6px;
            padding: 7px 10px;
            background-color: #ffffff;
            selection-background-color: #409eff;
        }
        QLineEdit:focus {
            border: 1px solid #409eff;
        }
        QPushButton {
            background-color: #ffffff;
            border: 1px solid #dcdfe6;
            border-radius: 6px;
            padding: 6px 14px;
            color: #303133;
            font-weight: 500;
        }
        QPushButton:hover {
            background-color: #ecf5ff;
            color: #409eff;
            border-color: #c6e2ff;
        }
        QPushButton:pressed {
            background-color: #d9ecff;
        }
        #btnStart {
            background-color: #1a73e8;
            color: #ffffff;
            font-size: 15px;
            font-weight: bold;
            border: none;
            border-radius: 6px;
        }
        #btnStart:hover {
            background-color: #1557b0;
        }
        #btnStart:pressed {
            background-color: #0d47a1;
        }
        #btnStart:disabled {
            background-color: #a0cfff;
            color: #f4f4f5;
        }
        #btnExit {
            background-color: #f56c6c;
            color: #ffffff;
            font-size: 14px;
            font-weight: bold;
            border: none;
            border-radius: 6px;
        }
        #btnExit:hover {
            background-color: #e64242;
        }
        #btnExit:pressed {
            background-color: #cb2d2d;
        }
        QProgressBar {
            border: 1px solid #e4e7ed;
            border-radius: 6px;
            background-color: #ebeef5;
            text-align: center;
            font-size: 11px;
            color: #303133;
        }
        QProgressBar::chunk {
            background-color: #409eff;
            border-radius: 5px;
        }
        QTextEdit {
            border: 1px solid #dcdfe6;
            border-radius: 6px;
            background-color: #ffffff;
            font-family: "Consolas", "Courier New", monospace;
            font-size: 12px;
            line-height: 1.4;
            padding: 8px;
        }
        #statusLabel {
            font-weight: 500;
            color: #409eff;
        }
        """
        self.setStyleSheet(style)

    # ==========================
    # 드래그 앤 드롭 이벤트
    # ==========================
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.isfile(file_path):
                self.input_edit.setText(file_path)
                event.acceptProposedAction()

    # ==========================
    # 파일 탐색 및 경로 연동
    # ==========================
    def browse_input_file(self):
        file_filter = (
            "모든 지원 파일 (*.docx *.hwp *.hwpx *.xlsx *.xls *.pptx *.ppt *.pdf *.txt *.html *.htm *.csv *.json *.xml);;"
            "한글 문서 (*.hwp *.hwpx);;"
            "Word 문서 (*.docx);;"
            "Excel 문서 (*.xlsx *.xls);;"
            "PowerPoint 문서 (*.pptx *.ppt);;"
            "PDF 문서 (*.pdf);;"
            "텍스트 문서 (*.txt);;"
            "모든 파일 (*.*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "변환할 파일 선택", "", file_filter
        )
        if file_path:
            self.input_edit.setText(os.path.normpath(file_path))

    def browse_output_file(self):
        current_out = self.output_edit.text().strip()
        start_dir = str(Path(current_out).parent) if current_out else ""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Markdown 저장 위치 선택", start_dir, "Markdown 파일 (*.md);;모든 파일 (*.*)"
        )
        if file_path:
            if not file_path.lower().endswith(".md"):
                file_path += ".md"
            self.output_edit.setText(os.path.normpath(file_path))

    def on_input_text_changed(self, text: str):
        clean_text = text.strip().strip('"').strip("'")
        if clean_text:
            p = Path(clean_text)
            default_out = p.with_suffix(".md")
            self.output_edit.setText(str(default_out))

    # ==========================
    # 변환 작업 제어
    # ==========================
    def start_conversion(self):
        input_path = self.input_edit.text().strip().strip('"').strip("'")
        output_path = self.output_edit.text().strip().strip('"').strip("'")

        if not input_path:
            QMessageBox.warning(self, "입력 오류", "변환할 입력 파일을 선택해주세요.")
            self.input_edit.setFocus()
            return

        if not os.path.isfile(input_path):
            QMessageBox.critical(self, "파일 오류", f"입력 파일을 찾을 수 없습니다:\n{input_path}")
            return

        if not output_path:
            QMessageBox.warning(self, "출력 오류", "출력 마크다운 파일 경로를 입력해주세요.")
            self.output_edit.setFocus()
            return

        self.btn_start.setEnabled(False)
        self.btn_browse_input.setEnabled(False)
        self.btn_browse_output.setEnabled(False)
        self.progress_bar.setValue(0)
        self.preview_edit.clear()

        include_summary = self.chk_summary.isChecked()
        self.worker = ConversionWorker(input_path, output_path, include_summary=include_summary)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_progress(self, val: int, message: str):
        self.progress_bar.setValue(val)
        self.status_label.setText(f"상태: {message}")

    def on_worker_finished(self, success: bool, message_or_content: str, out_path: str, elapsed: float):
        self.btn_start.setEnabled(True)
        self.btn_browse_input.setEnabled(True)
        self.btn_browse_output.setEnabled(True)

        if success:
            self.status_label.setText(f"상태: ✅ 변환 및 요약 완료! ({elapsed}초 소요)")
            if self.chk_preview.isChecked():
                self.preview_edit.setPlainText(message_or_content)

            QMessageBox.information(
                self, "변환 성공",
                f"마크다운 변환 및 핵심 요약이 완료되었습니다!\n\n저장 경로:\n{out_path}\n소요 시간: {elapsed}초"
            )

            if self.chk_open_folder.isChecked():
                self.open_target_folder()
        else:
            self.status_label.setText("상태: ❌ 변환 실패")
            QMessageBox.critical(
                self, "변환 오류",
                f"문서 변환 중 오류가 발생했습니다:\n\n{message_or_content}"
            )

    # ==========================
    # 보조 기능 (복사, 파일/폴더 열기)
    # ==========================
    def copy_preview_to_clipboard(self):
        text = self.preview_edit.toPlainText()
        if not text:
            QMessageBox.information(self, "알림", "복사할 마크다운 내용이 없습니다.")
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            QMessageBox.information(self, "완료", "마크다운 내용이 클립보드에 복사되었습니다.")

    def open_generated_file(self):
        out_path = self.output_edit.text().strip().strip('"').strip("'")
        if out_path and os.path.isfile(out_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(out_path))
        else:
            QMessageBox.warning(self, "경고", "열 수 있는 마크다운 파일이 존재하지 않습니다.")

    def open_target_folder(self):
        out_path = self.output_edit.text().strip().strip('"').strip("'")
        if out_path:
            folder = os.path.dirname(os.path.abspath(out_path))
            if os.path.isdir(folder):
                if sys.platform == "win32":
                    subprocess.run(["explorer", folder])
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
                return
        QMessageBox.warning(self, "경고", "저장 폴더를 찾을 수 없습니다.")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MarkItDownGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
