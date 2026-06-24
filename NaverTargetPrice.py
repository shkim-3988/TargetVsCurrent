import sys
import csv
import logging
from typing import Dict, Any, List
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QAxContainer import QAxWidget


########################################################
# Logging
########################################################
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


########################################################
# Utility
########################################################
def safe_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except:
        return 0.0


def is_common_stock(code: str, name: str) -> bool:
    if not code.isdigit():
        return False
    if code[-1] in ['5', '6', '7', '8', '9']:
        return False
    upper = name.upper()
    bad_words = ["ETF", "ETN", "SPAC", "스팩", "리츠", "REIT", "우선주"]
    return not any(w in upper for w in bad_words)


########################################################
# Naver 목표가 크롤링 (분리 전 방식 그대로)
########################################################
def get_naver_target_price_html(code: str) -> float:
    url = f"https://finance.naver.com/item/main.naver?code={code}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://finance.naver.com/",
    }

    try:
        r = requests.get(url, headers=headers, timeout=5)

        # ★ 분리 전 코드와 동일하게 r.text 사용
        soup = BeautifulSoup(r.text, "html.parser")

        th_list = soup.find_all("th")
        for th in th_list:
            if "목표주가" in th.get_text():
                td = th.find_next_sibling("td")
                if not td:
                    continue
                em_tags = td.find_all("em")
                if len(em_tags) >= 2:
                    return safe_float(em_tags[-1].text)

        return 0.0

    except Exception as e:
        logger.warning(f"[{code}] 네이버 목표가 크롤링 실패: {e}")
        return 0.0


########################################################
# Thread
########################################################
class NaverCrawlerThread(QThread):
    progress_update = pyqtSignal(int, int, dict)  # ★ 실시간 업데이트용
    finished_with_data = pyqtSignal(dict)

    def __init__(self, stock_list: List[Dict[str, str]]):
        super().__init__()
        self.stock_list = stock_list

    def run(self):
        result = {}
        total = len(self.stock_list)

        for i, item in enumerate(self.stock_list):
            code = item["code"]
            tp = get_naver_target_price_html(code)
            if tp > 0:
                result[code] = tp

            # ★ 실시간 업데이트 신호
            self.progress_update.emit(i + 1, total, result)

        self.finished_with_data.emit(result)


########################################################
# OpenAPI 종목 리스트 로더
########################################################
class KiwoomCodeLoader:
    def __init__(self, gui: QWidget):
        self.gui = gui

        self.ocx = QAxWidget(gui)
        self.ocx.setControl("KHOPENAPI.KHOpenAPICtrl.1")
        gui.layout().addWidget(self.ocx)
        self.ocx.setVisible(False)

        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.dynamicCall("CommConnect()")

    def _on_event_connect(self, err_code):
        if err_code == 0:
            logger.info("키움 로그인 성공 (종목 리스트 로딩)")
            self.load_codes()
        else:
            QMessageBox.critical(self.gui, "로그인 실패", f"키움 로그인 실패 (코드: {err_code})")

    def load_codes(self):
        kospi = self.ocx.dynamicCall("GetCodeListByMarket(QString)", "0").split(";")
        kosdaq = self.ocx.dynamicCall("GetCodeListByMarket(QString)", "10").split(";")

        stock_list = []

        for code in kospi + kosdaq:
            code = code.strip()
            if not code:
                continue

            raw = self.ocx.dynamicCall("GetMasterCodeName(QString)", code)
            name = raw.encode("latin1").decode("euc-kr")

            if not is_common_stock(code, name):
                continue

            market = "KOSPI" if code in kospi else "KOSDAQ"

            stock_list.append({
                "code": code,
                "name": name,
                "market": market
            })

        logger.info(f"OpenAPI 종목 로딩 완료: {len(stock_list)}개")
        self.gui.on_codes_loaded(stock_list)


########################################################
# GUI
########################################################
class NaverTargetCrawlerGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("네이버 목표가 크롤러 (자동 실행 버전)")
        self.resize(900, 700)

        self.stock_list = []
        self.target_cache = {}
        self.filename = ""

        self.init_ui()

        # ★ 프로그램 실행 시 자동으로 Kiwoom 로딩 → 자동 크롤링 시작
        self.kiwoom_loader = KiwoomCodeLoader(self)

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        group_status = QGroupBox("진행 상태")
        status_layout = QVBoxLayout()

        self.label_status = QLabel("OpenAPI 로그인 및 종목 리스트 로딩 중...")
        status_layout.addWidget(self.label_status)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(22)
        status_layout.addWidget(self.progress)

        group_status.setLayout(status_layout)
        layout.addWidget(group_status)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["시장", "종목코드", "종목명", "목표가"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    ####################################################
    # 종목 로딩 완료 → 자동 크롤링 시작
    ####################################################
    def on_codes_loaded(self, stock_list):
        self.stock_list = stock_list
        self.label_status.setText(f"종목 로딩 완료 — {len(stock_list):,}개")
        self.progress.setMaximum(len(stock_list))
        self.progress.setValue(0)

        # ★ 자동으로 크롤링 시작
        QTimer.singleShot(500, self.start_crawling)

    ####################################################
    # 크롤링 시작
    ####################################################
    def start_crawling(self):
        self.label_status.setText("네이버 목표가 수집 중...")

        self.crawler_thread = NaverCrawlerThread(self.stock_list)
        self.crawler_thread.progress_update.connect(self.on_progress_update)
        self.crawler_thread.finished_with_data.connect(self.on_crawling_done)
        self.crawler_thread.start()

    ####################################################
    # 실시간 업데이트
    ####################################################
    def on_progress_update(self, current, total, result):
        self.progress.setValue(current)
        self.label_status.setText(f"수집 중... {current:,} / {total:,}")

        # ★ 실시간 테이블 업데이트
        self.update_table_live(result)

    ####################################################
    # 최종 완료
    ####################################################
    def on_crawling_done(self, target_cache):
        self.target_cache = target_cache
        self.label_status.setText(f"완료 — 목표가 존재 종목: {len(target_cache):,}개")

        self.save_to_csv(target_cache)

        QMessageBox.information(self, "완료", f"저장됨: {self.filename}")

    ####################################################
    # 실시간 테이블 갱신
    ####################################################
    def update_table_live(self, result):
        items = []
        for item in self.stock_list:
            code = item["code"]
            if code in result:
                items.append({
                    "market": item["market"],
                    "code": code,
                    "name": item["name"],
                    "target": result[code]
                })

        self.table.setRowCount(len(items))
        for i, data in enumerate(items):
            self.table.setItem(i, 0, QTableWidgetItem(data["market"]))
            self.table.setItem(i, 1, QTableWidgetItem(data["code"]))
            self.table.setItem(i, 2, QTableWidgetItem(data["name"]))
            self.table.setItem(i, 3, QTableWidgetItem(f"{int(data['target']):,}"))

    ####################################################
    # CSV 저장
    ####################################################
    def save_to_csv(self, result):
        today = datetime.now().strftime("%Y%m%d")
        self.filename = f"목표가_{today}.csv"

        with open(self.filename, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["시장", "종목코드", "종목명", "목표가"])

            for item in self.stock_list:
                code = item["code"]
                if code in result:
                    writer.writerow([
                        item["market"],
                        code,
                        item["name"],
                        int(result[code])
                    ])


########################################################
# Main
########################################################
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = NaverTargetCrawlerGUI()
    gui.show()
    sys.exit(app.exec_())
