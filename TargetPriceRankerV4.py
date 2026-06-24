import sys
import csv
import logging
from collections import deque
from typing import Dict, Any, List
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QPushButton, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer
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


def to_eok(value):
    try:
        return float(value) / 100_000_000
    except:
        return 0.0


########################################################
# Data Manager
########################################################
class AnalysisManager:
    def __init__(self):
        self.stock_data: Dict[str, Dict[str, Any]] = {}
        self.target_cache: Dict[str, float] = {}

    def update(self, code, name, market, current, target_price,
               prev_close, volume, amount_million, shares, market_cap):

        upside = 0.0
        if current > 0 and target_price > 0:
            upside = (target_price - current) / current * 100

        self.stock_data[code] = {
            "code": code,
            "name": name,
            "market": market,
            "current": current,
            "target": target_price,
            "upside": upside,
            "prev_close": prev_close,
            "volume": volume,
            "amount": amount_million,
            "shares": shares,
            "market_cap": market_cap
        }

    def get_ranked_list(self):
        items = []
        for code, info in self.stock_data.items():
            if info["target"] > 0:
                items.append(info)
        return sorted(items, key=lambda x: x["upside"], reverse=True)


########################################################
# Kiwoom TR 수집기
########################################################
class Kiwoom(QAxWidget):
    TR_INTERVAL = 1200  # ms

    def __init__(self, manager: AnalysisManager, gui: QWidget):
        super().__init__(gui)
        self.manager = manager
        self.gui = gui

        # 이 객체 자체가 OpenAPI 컨트롤
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")
        gui.layout().addWidget(self)
        self.setVisible(False)

        self.codes: List[str] = []
        self.name_map: Dict[str, str] = {}
        self.market_map: Dict[str, str] = {}

        self.queue = deque()
        self.is_tr_running = False
        self.tr_total = 0
        self.tr_count = 0

        self.temp_prev_data: Dict[str, Any] = {}

        self.OnEventConnect.connect(self._on_event_connect)
        self.OnReceiveTrData.connect(self._on_receive_tr_data)

        self.dynamicCall("CommConnect()")

    ####################################################
    # 로그인 완료
    ####################################################
    def _on_event_connect(self, err_code):
        if err_code == 0:
            logger.info("키움 로그인 성공 (프로그램 B)")
            self.gui.on_login_success()
        else:
            QMessageBox.critical(self.gui, "로그인 실패", f"키움 로그인 실패 (코드: {err_code})")

    ####################################################
    # 외부에서 TR 시작 요청
    ####################################################
    def start_tr(self, codes: List[str],
                 name_map: Dict[str, str],
                 market_map: Dict[str, str]):
        if not codes:
            QMessageBox.warning(self.gui, "경고", "TR 수집 대상 종목이 없습니다.")
            return

        self.codes = codes
        self.name_map = name_map
        self.market_map = market_map

        self.tr_total = len(codes)
        self.tr_count = 0
        self.queue.clear()

        for code in codes:
            self.queue.append(code)

        self.gui.set_phase("tr", self.tr_total)
        self.process_tr_queue()

    ####################################################
    # TR 큐 처리
    ####################################################
    def process_tr_queue(self):
        if self.is_tr_running or not self.queue:
            if not self.queue:
                self.gui.set_phase("done")
                self.gui.update_table()  # 최종 Upside 기준 정렬 결과
            return

        code = self.queue.popleft()
        self.is_tr_running = True

        name = self.name_map.get(code, "")
        self.gui.update_tr_current_stock(code, name)

        screen = "8001"

        self.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.dynamicCall("CommRqData(QString, QString, int, QString)",
                         "기본정보요청", "opt10007", 0, screen)

    ####################################################
    # TR 응답 처리
    ####################################################
    def _on_receive_tr_data(self, screen_no, rqname, trcode, recordname, prev_next, *args):
        print(f"[TR 수신] rqname={rqname}")

        if rqname == "기본정보요청":
            raw_code = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "종목코드").strip()
            code = raw_code[-6:]

            prev_close = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "전일종가"))
            prev_volume = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "전일거래량"))
            prev_amount_million = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "전일거래대금"))
            today_amount_million = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "거래대금"))
            shares_thousand = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "상장주식수"))

            shares = shares_thousand * 1000
            market_cap = prev_close * shares

            self.temp_prev_data = {
                "prev_close": prev_close,
                "prev_volume": prev_volume,
                "prev_amount_million": prev_amount_million,
                "today_amount_million": today_amount_million,
                "shares": shares,
                "market_cap": market_cap
            }

            QTimer.singleShot(self.TR_INTERVAL, lambda: self.request_opt10001(code))
            return

        if rqname == "현재가요청":
            raw_code = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "종목코드").strip()
            code = raw_code[-6:]

            name = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "종목명").strip()
            current = abs(safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "현재가")))
            volume = safe_float(self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "거래량"))

            market = self.market_map.get(code, "UNKNOWN")
            target_price = self.manager.target_cache.get(code, 0.0)
            prev = self.temp_prev_data

            self.manager.update(
                code, name, market, current, target_price,
                prev["prev_close"], volume,
                prev["today_amount_million"],
                prev["shares"], prev["market_cap"]
            )

            self.tr_count += 1
            self.gui.update_tr_progress(self.tr_count, self.tr_total, code, name)

            # 실시간 테이블 업데이트
            self.gui.update_table_live()

            self.is_tr_running = False
            QTimer.singleShot(self.TR_INTERVAL, self.process_tr_queue)

    ####################################################
    def request_opt10001(self, code):
        screen = "9001"
        self.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.dynamicCall("CommRqData(QString, QString, int, QString)",
                         "현재가요청", "opt10001", 0, screen)


########################################################
# GUI
########################################################
class TargetPriceRankerGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("목표가 Upside 랭킹 (프로그램 B)")
        self.resize(1300, 860)

        self.manager = AnalysisManager()
        self.kiwoom: Kiwoom | None = None

        self.codes: List[str] = []
        self.name_map: Dict[str, str] = {}
        self.market_map: Dict[str, str] = {}

        self.filename = ""
        self._tr_start_time: datetime | None = None

        self.init_ui()
        QTimer.singleShot(1000, self.init_kiwoom)

    ####################################################
    # UI 구성
    ####################################################
    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # CSV 로드 버튼
        btn_layout_top = QHBoxLayout()
        self.btn_load_csv = QPushButton("① 목표가 CSV 불러오기")
        self.btn_load_csv.clicked.connect(self.load_target_csv)
        self.btn_load_csv.setEnabled(False)
        btn_layout_top.addWidget(self.btn_load_csv)
        btn_layout_top.addStretch()
        layout.addLayout(btn_layout_top)

        # CSV 상태 그룹
        naver_group = QGroupBox("① 목표가 CSV 상태")
        naver_layout = QVBoxLayout()
        self.label_naver_status = QLabel("키움 로그인 후 CSV를 불러주세요.")
        naver_layout.addWidget(self.label_naver_status)
        naver_group.setLayout(naver_layout)
        layout.addWidget(naver_group)

        # TR 수집 그룹
        tr_group = QGroupBox("② OpenAPI TR 데이터 수집")
        tr_layout = QVBoxLayout()

        tr_top = QHBoxLayout()
        self.label_tr_status = QLabel("대기 중...")
        tr_top.addWidget(self.label_tr_status)
        tr_top.addStretch()
        self.label_tr_current = QLabel("")
        self.label_tr_current.setStyleSheet("color: #0055aa; font-weight: bold;")
        tr_top.addWidget(self.label_tr_current)
        tr_layout.addLayout(tr_top)

        self.progress_tr = QProgressBar()
        self.progress_tr.setFormat("%v / %m  (%p%)")
        self.progress_tr.setFixedHeight(22)
        tr_layout.addWidget(self.progress_tr)

        self.label_tr_eta = QLabel("예상 잔여시간: -")
        self.label_tr_eta.setStyleSheet("color: gray; font-size: 11px;")
        tr_layout.addWidget(self.label_tr_eta)

        tr_group.setLayout(tr_layout)
        layout.addWidget(tr_group)

        # 결과 테이블
        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "순위", "시장", "종목코드", "종목명",
            "현재가", "목표가", "상승여력(%)",
            "전일종가", "거래량", "거래대금(백만원)",
            "상장주식수(주)", "시가총액(억원)"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    ####################################################
    # Kiwoom 초기화
    ####################################################
    def init_kiwoom(self):
        self.kiwoom = Kiwoom(self.manager, self)

    def on_login_success(self):
        self.label_naver_status.setText("키움 로그인 완료. CSV 파일을 불러주세요.")
        self.btn_load_csv.setEnabled(True)

    ####################################################
    # CSV 로드
    ####################################################
    def load_target_csv(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "목표가 CSV 선택", "", "CSV Files (*.csv)"
        )
        if not file:
            return

        target_cache: Dict[str, float] = {}
        name_map: Dict[str, str] = {}
        market_map: Dict[str, str] = {}

        try:
            with open(file, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    market = row.get("시장", "").strip()
                    code = row.get("종목코드", "").strip()
                    name = row.get("종목명", "").strip()
                    tp = safe_float(row.get("목표가", 0))

                    if not code or tp <= 0:
                        continue

                    target_cache[code] = tp
                    name_map[code] = name
                    market_map[code] = market

        except Exception as e:
            QMessageBox.critical(self, "오류", f"CSV 로딩 실패: {e}")
            return

        self.manager.target_cache = target_cache
        self.name_map = name_map
        self.market_map = market_map
        self.codes = list(target_cache.keys())

        self.label_naver_status.setText(
            f"CSV 로드 완료 — 목표가 존재 종목: {len(self.codes):,}개"
        )

        if self.kiwoom:
            self.start_tr()

    ####################################################
    # TR 시작
    ####################################################
    def start_tr(self):
        if not self.codes:
            QMessageBox.warning(self, "경고", "TR 수집 대상 종목이 없습니다.")
            return

        self.set_phase("tr", len(self.codes))
        self.kiwoom.start_tr(self.codes, self.name_map, self.market_map)

    ####################################################
    # 단계 전환
    ####################################################
    def set_phase(self, phase: str, total: int = 0):
        if phase == "tr":
            self.label_tr_status.setText(f"OpenAPI TR 수집 시작 (총 {total:,}종목)")
            self.progress_tr.setMaximum(total)
            self.progress_tr.setValue(0)
            self.label_tr_current.setText("")
            self.label_tr_eta.setText("예상 잔여시간: 계산 중...")
            self._tr_start_time = datetime.now()

        elif phase == "done":
            self.label_tr_status.setText("✅ TR 수집 완료")
            self.label_tr_current.setText("")
            self.label_tr_eta.setText("")

    ####################################################
    # TR 진행 업데이트
    ####################################################
    def update_tr_current_stock(self, code: str, name: str):
        if name:
            self.label_tr_current.setText(f"수집 중: [{code}] {name}")
        else:
            self.label_tr_current.setText(f"수집 중: [{code}]")

    def update_tr_progress(self, current: int, total: int, code: str, name: str):
        self.progress_tr.setValue(current)

        eta_str = ""
        if self._tr_start_time and current > 0:
            elapsed = (datetime.now() - self._tr_start_time).total_seconds()
            remaining = (elapsed / current) * (total - current)
            mins, secs = divmod(int(remaining), 60)
            if mins > 0:
                eta_str = f"예상 잔여시간: 약 {mins}분 {secs}초"
            else:
                eta_str = f"예상 잔여시간: 약 {secs}초"

        self.label_tr_eta.setText(eta_str)
        self.label_tr_status.setText(
            f"OpenAPI TR 수집 중...  {current:,} / {total:,}종목 완료"
        )
        self.label_tr_current.setText(f"완료: [{code}] {name}")

    ####################################################
    # 실시간 테이블 갱신 (수집 중)
    ####################################################
    def update_table_live(self):
        data_list = list(self.manager.stock_data.values())
        self.table.setRowCount(len(data_list))

        for i, data in enumerate(data_list):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(data["market"]))
            self.table.setItem(i, 2, QTableWidgetItem(data["code"]))
            self.table.setItem(i, 3, QTableWidgetItem(data["name"]))
            self.table.setItem(i, 4, QTableWidgetItem(f"{int(data['current']):,}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{int(data['target']):,}"))

            up_item = QTableWidgetItem(f"{data['upside']:.2f}%")
            if data["upside"] > 0:
                up_item.setForeground(Qt.red)
            elif data["upside"] < 0:
                up_item.setForeground(Qt.blue)
            self.table.setItem(i, 6, up_item)

    ####################################################
    # 최종 테이블 갱신 (Upside 정렬 결과)
    ####################################################
    def update_table(self):
        ranked_list = self.manager.get_ranked_list()

        kospi_list = sorted(
            [x for x in ranked_list if x["market"] == "KOSPI"],
            key=lambda x: x["upside"], reverse=True
        )
        kosdaq_list = sorted(
            [x for x in ranked_list if x["market"] == "KOSDAQ"],
            key=lambda x: x["upside"], reverse=True
        )
        ranked_list = kospi_list + kosdaq_list

        if not ranked_list:
            self.label_tr_status.setText("조회 완료: 목표가 데이터 없음")
            return

        self.table.setRowCount(len(ranked_list))

        for i, data in enumerate(ranked_list):
            self.table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.table.setItem(i, 1, QTableWidgetItem(data["market"]))
            self.table.setItem(i, 2, QTableWidgetItem(data["code"]))
            self.table.setItem(i, 3, QTableWidgetItem(data["name"]))
            self.table.setItem(i, 4, QTableWidgetItem(f"{int(data['current']):,}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{int(data['target']):,}"))

            up_item = QTableWidgetItem(f"{data['upside']:.2f}%")
            if data["upside"] > 0:
                up_item.setForeground(Qt.red)
            elif data["upside"] < 0:
                up_item.setForeground(Qt.blue)
            self.table.setItem(i, 6, up_item)

            self.table.setItem(i, 7, QTableWidgetItem(f"{int(data['prev_close']):,}"))
            self.table.setItem(i, 8, QTableWidgetItem(f"{int(data['volume']):,}"))
            self.table.setItem(i, 9, QTableWidgetItem(f"{data['amount']:,.2f}"))
            self.table.setItem(i, 10, QTableWidgetItem(f"{int(data['shares']):,}"))
            self.table.setItem(i, 11, QTableWidgetItem(f"{to_eok(data['market_cap']):,.2f}"))

        self.label_tr_status.setText(f"✅ 조회 완료: {len(ranked_list):,}종목")
        self.save_to_csv(ranked_list)
        QMessageBox.information(self, "완료", f"조사 완료!\n'{self.filename}'로 저장되었습니다.")

    ####################################################
    # CSV 저장
    ####################################################
    def save_to_csv(self, ranked_list):
        today = datetime.now().strftime("%Y%m%d")
        self.filename = f"목표가_vs_현재가_{today}.csv"

        with open(self.filename, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "순위", "시장", "종목코드", "종목명",
                "현재가", "목표가", "상승여력(%)",
                "전일종가", "거래량", "거래대금(백만원)",
                "상장주식수(주)", "시가총액(억원)"
            ])
            for i, data in enumerate(ranked_list):
                writer.writerow([
                    i + 1, data["market"], data["code"], data["name"],
                    data["current"], data["target"],
                    f"{data['upside']:.2f}%",
                    data["prev_close"], data["volume"],
                    f"{data['amount']:,.2f}",
                    data["shares"],
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
