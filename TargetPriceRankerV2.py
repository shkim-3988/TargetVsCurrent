import sys
import csv
import logging
from collections import deque
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
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
    """보통주만 남기고 ETF/ETN/우선주/특수상품 제거"""
    if not code.isdigit():
        return False
    if code[-1] in ['5', '6', '7', '8', '9']:
        return False
    upper = name.upper()
    etf_words = ["ETF", "ETN", "인버스", "LEVERAGE", "레버리지", "커버드콜", "액티브", "밸런스"]
    if any(w in upper for w in etf_words):
        return False
    return True


# ⭐ 시가총액 → 억원 단위 변환
def to_eok(value):
    try:
        v = float(value)
    except:
        return 0.0
    return v / 100_000_000


# ⭐ 거래대금 → 천원 단위 변환
def to_thousand(value):
    try:
        v = float(value)
    except:
        return 0.0
    return v / 1000


########################################################
# Naver 목표가 크롤링
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

    except Exception:
        return 0.0


########################################################
# Data Manager
########################################################
class AnalysisManager:
    def __init__(self):
        self.stock_data: Dict[str, Dict[str, Any]] = {}
        self.valid_count = 0
        self.target_cache: Dict[str, float] = {}

    def preload_targets(self, codes: List[str], max_workers: int = 10):
        logger.info(f"네이버 목표가 멀티스레드 수집 시작 (종목 수: {len(codes)}, workers={max_workers})")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(get_naver_target_price_html, code): code
                for code in codes
            }
            total = len(codes)
            for i, future in enumerate(as_completed(future_to_code), start=1):
                code = future_to_code[future]
                try:
                    target = future.result()
                except Exception:
                    target = 0.0
                self.target_cache[code] = target

                if i % 100 == 0 or i == total:
                    logger.info(f"네이버 목표가 수집 진행률: {i}/{total}")

        logger.info("네이버 목표가 수집 완료")

    def update(self, code, name, market, current, target_price,
               prev_close, volume, amount, shares, market_cap):

        upside = 0.0
        if current > 0 and target_price > 0:
            upside = (target_price - current) / current * 100

        self.stock_data[code] = {
            "name": name,
            "market": market,
            "current": current,
            "target": target_price,
            "upside": upside,
            "prev_close": prev_close,
            "volume": volume,
            "amount": amount,
            "shares": shares,
            "market_cap": market_cap
        }

        if target_price > 0:
            self.valid_count += 1

    def get_ranked_list(self):
        items = []
        for code, info in self.stock_data.items():
            if info["target"] > 0:
                items.append({"code": code, **info})
        return sorted(items, key=lambda x: x["upside"], reverse=True)


########################################################
# Naver Thread
########################################################
class NaverTargetThread(QThread):
    finished = pyqtSignal()

    def __init__(self, manager: AnalysisManager, codes: List[str]):
        super().__init__()
        self.manager = manager
        self.codes = codes

    def run(self):
        self.manager.preload_targets(self.codes)
        self.finished.emit()


########################################################
# Kiwoom API Wrapper
########################################################
class Kiwoom(QAxWidget):
    TR_INTERVAL = 500  # ms (Kiwoom TR 간격, 너무 빠르면 오류 발생 가능성 있음)

    def __init__(self, manager: AnalysisManager, gui):
        super().__init__()
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")

        self.manager = manager
        self.gui = gui

        self.market_map: Dict[str, str] = {}
        self.codes: List[str] = []
        self.queue = deque()
        self.is_tr_running = False
        self.tr_total = 0
        self.tr_count = 0

        # opt10007에서 받은 전일 데이터 임시 저장용
        self.temp_prev_data: Dict[str, Any] = {}

        self.naver_thread: NaverTargetThread | None = None

        self.OnEventConnect.connect(self._on_event_connect)
        self.OnReceiveTrData.connect(self._on_receive_tr_data)

        self.dynamicCall("CommConnect()")

    def _on_event_connect(self, err_code):
        if err_code == 0:
            logger.info("로그인 성공")
            self.start_analysis()
        else:
            logger.error(f"로그인 실패: {err_code}")

    def start_analysis(self):
        kospi = [c for c in self.dynamicCall("GetCodeListByMarket(QString)", "0").split(';') if c]
        kosdaq = [c for c in self.dynamicCall("GetCodeListByMarket(QString)", "10").split(';') if c]

        filtered = []
        for code in kospi + kosdaq:
            name = self.dynamicCall("GetMasterCodeName(QString)", code)
            if is_common_stock(code, name):
                filtered.append(code)
                self.market_map[code] = "KOSPI" if code in kospi else "KOSDAQ"

        self.codes = filtered
        self.tr_total = len(self.codes)

        self.gui.label_status.setText("네이버 목표가 수집 중...")
        self.naver_thread = NaverTargetThread(self.manager, self.codes)
        self.naver_thread.finished.connect(self._on_naver_done)
        self.naver_thread.start()

    def _on_naver_done(self):
        self.gui.label_status.setText("Kiwoom TR 수집 시작...")

        for code in self.codes:
            self.queue.append(code)

        self.process_tr_queue()

    def process_tr_queue(self):
        if self.is_tr_running or not self.queue:
            if not self.queue:
                self.gui.update_table()
            return

        code = self.queue.popleft()
        self.is_tr_running = True

        # ⭐ 1단계: opt10007 먼저 요청 (전일 데이터 + 상장주식수)
        self.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.dynamicCall("CommRqData(QString, QString, int, QString)",
                         "기본정보요청", "opt10007", 0, "8001")

    def _on_receive_tr_data(self, screen_no, rqname, trcode, recordname, prev_next, *args):

        # ==========================================
        # 1) opt10007 처리 (전일 데이터)
        # ==========================================
        if rqname == "기본정보요청":
            raw_code = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "종목코드"
            ).strip()
            code = raw_code[-6:]

            prev_close = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "전일종가"
            ))

            prev_volume = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "전일거래량"
            ))

            prev_amount = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "전일거래대금"
            ))

            shares_thousand = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "상장주식수"
            ))

            # 천주 → 주
            shares = shares_thousand * 1000

            # ⭐ B 방식: 시가총액 직접 계산
            market_cap = prev_close * shares

            self.temp_prev_data = {
                "code": code,
                "prev_close": prev_close,
                "prev_volume": prev_volume,
                "prev_amount": prev_amount,
                "shares": shares,
                "market_cap": market_cap
            }

            # 다음 단계: opt10001 요청 (당일 데이터)
            self.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
            self.dynamicCall("CommRqData(QString, QString, int, QString)",
                             "현재가요청", "opt10001", 0, "9001")
            return

        # ==========================================
        # 2) opt10001 처리 (당일 데이터)
        # ==========================================
        if rqname == "현재가요청":
            raw_code = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "종목코드"
            ).strip()
            code = raw_code[-6:]

            name = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "종목명"
            ).strip()

            current = abs(safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "현재가"
            )))

            volume = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "거래량"
            ))

            amount = abs(safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "거래대금"
            )))

            market = self.market_map.get(code, "UNKNOWN")
            target_price = self.manager.target_cache.get(code, 0.0)

            prev = self.temp_prev_data

            self.manager.update(
                code,
                name,
                market,
                current,
                target_price,
                prev["prev_close"],
                volume,
                amount,
                prev["shares"],
                prev["market_cap"]
            )

            self.tr_count += 1
            self.gui.update_progress(self.tr_count, self.tr_total, self.manager.valid_count)

            self.is_tr_running = False
            QTimer.singleShot(self.TR_INTERVAL, self.process_tr_queue)


########################################################
# GUI
########################################################
class TargetPriceRankerGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.manager = AnalysisManager()
        self.kiwoom: Kiwoom | None = None

        self.init_ui()
        QTimer.singleShot(500, self.init_kiwoom)

    def init_ui(self):
        self.setWindowTitle("목표가 Upside 랭킹 V2 (시가총액 억원 / 거래대금 천원)")
        self.resize(1300, 800)

        layout = QVBoxLayout()

        self.label_status = QLabel("로그인 대기 중...")
        layout.addWidget(self.label_status)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "순위", "시장", "종목코드", "종목명",
            "현재가", "목표가", "상승여력(%)",
            "전일종가", "거래량", "거래대금(천원)",
            "상장주식수", "시가총액(억원)"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def init_kiwoom(self):
        self.kiwoom = Kiwoom(self.manager, self)

    def update_progress(self, current, total, valid_count):
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self.label_status.setText(
            f"수집 중: {current}/{total} (목표가 존재: {valid_count})"
        )

    def update_table(self):
        ranked_list = self.manager.get_ranked_list()

        kospi_list = [item for item in ranked_list if item["market"] == "KOSPI"]
        kosdaq_list = [item for item in ranked_list if item["market"] == "KOSDAQ"]

        kospi_list.sort(key=lambda x: x["upside"], reverse=True)
        kosdaq_list.sort(key=lambda x: x["upside"], reverse=True)

        ranked_list = kospi_list + kosdaq_list

        if not ranked_list:
            self.label_status.setText("조회 완료: 목표가 데이터 없음")
            return

        self.table.setRowCount(len(ranked_list))

        for i, data in enumerate(ranked_list):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(data['market']))
            self.table.setItem(i, 2, QTableWidgetItem(data['code']))
            self.table.setItem(i, 3, QTableWidgetItem(data['name']))
            self.table.setItem(i, 4, QTableWidgetItem(f"{int(data['current']):,}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{int(data['target']):,}"))

            up_item = QTableWidgetItem(f"{data['upside']:.2f}%")
            if data['upside'] > 0:
                up_item.setForeground(Qt.red)
            elif data['upside'] < 0:
                up_item.setForeground(Qt.blue)
            self.table.setItem(i, 6, up_item)

            self.table.setItem(i, 7, QTableWidgetItem(f"{int(data['prev_close']):,}"))
            self.table.setItem(i, 8, QTableWidgetItem(f"{int(data['volume']):,}"))

            # ⭐ 거래대금 → 천원 단위
            amount_thousand = to_thousand(data['amount'])
            self.table.setItem(i, 9, QTableWidgetItem(f"{amount_thousand:,.2f}"))

            self.table.setItem(i, 10, QTableWidgetItem(f"{int(data['shares']):,}"))

            # ⭐ 시가총액 → 억원 단위
            market_cap_eok = to_eok(data['market_cap'])
            self.table.setItem(i, 11, QTableWidgetItem(f"{market_cap_eok:,.2f}"))

        self.label_status.setText(f"조회 완료: {len(ranked_list)} 종목")
        self.save_to_csv(ranked_list)
        QMessageBox.information(self, "완료", f"조사 완료! '{self.filename}'로 저장되었습니다.")

    def save_to_csv(self, ranked_list):
        today = datetime.now().strftime("%Y%m%d")
        self.filename = f"목표가_vs_현재가_V2_{today}.csv"
        with open(self.filename, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "순위", "시장", "종목코드", "종목명",
                "현재가", "목표가", "상승여력(%)",
                "전일종가", "거래량", "거래대금(천원)",
                "상장주식수", "시가총액(억원)"
            ])
            for i, data in enumerate(ranked_list):
                writer.writerow([
                    i + 1,
                    data['market'],
                    data['code'],
                    data['name'],
                    data['current'],
                    data['target'],
                    f"{data['upside']:.2f}%",
                    data['prev_close'],
                    data['volume'],
                    f"{to_thousand(data['amount']):.2f}",
                    data['shares'],
                    f"{to_eok(data['market_cap']):.2f}"
                ])


########################################################
# Main
########################################################
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = TargetPriceRankerGUI()
    gui.show()
    sys.exit(app.exec_())
