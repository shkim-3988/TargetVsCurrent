import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget

def to_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except:
        return 0.0

class KiwoomTest(QAxWidget):
    def __init__(self):
        super().__init__()
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")

        self.OnEventConnect.connect(self.on_login)
        self.OnReceiveTrData.connect(self.on_receive_tr)

        self.step = 0
        self.data = {}

        print("로그인 시도 중...")
        self.dynamicCall("CommConnect()")

    def on_login(self, err_code):
        if err_code == 0:
            print("로그인 성공")
            self.request_opt10007()
        else:
            print("로그인 실패:", err_code)

    def request_opt10007(self):
        code = "005930"
        print(f"\n[요청] opt10007 - {code}")

        self.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.dynamicCall("CommRqData(QString, QString, int, QString)",
                         "기본정보요청", "opt10007", 0, "7001")

    def request_opt10001(self):
        code = "005930"
        print(f"\n[요청] opt10001 - {code}")

        self.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.dynamicCall("CommRqData(QString, QString, int, QString)",
                         "현재가요청", "opt10001", 0, "7002")

    def on_receive_tr(self, screen_no, rqname, trcode, recordname, prev_next):

        # -------------------------------
        # 1) opt10007 처리
        # -------------------------------
        if rqname == "기본정보요청":
            def get(f):
                return self.dynamicCall(
                    "GetCommData(QString, QString, int, QString)",
                    trcode, rqname, 0, f
                ).strip()

            prev_close = to_float(get("전일종가"))
            shares_thousand = to_float(get("상장주식수"))

            self.data["prev_close"] = prev_close
            self.data["shares"] = shares_thousand * 1000  # 천주 → 주

            print("\n===== opt10007 결과 =====")
            print("전일종가:", prev_close)
            print("상장주식수(천주):", shares_thousand)
            print("상장주식수(주):", self.data["shares"])

            # 다음 단계: opt10001 요청
            self.request_opt10001()
            return

        # -------------------------------
        # 2) opt10001 처리
        # -------------------------------
        if rqname == "현재가요청":
            def get_idx(idx):
                return self.dynamicCall(
                    "GetCommData(QString, QString, int, int)",
                    trcode, rqname, 0, idx
                ).strip()

            market_cap_million = to_float(get_idx(9))  # 시가총액(백만원)

            self.data["market_cap_opt10001"] = market_cap_million * 1_000_000

            print("\n===== opt10001 결과 =====")
            print("시가총액(백만원):", market_cap_million)
            print("시가총액(원):", self.data["market_cap_opt10001"])

            # -------------------------------
            # 3) 계산된 시가총액 비교
            # -------------------------------
            calc_market_cap = self.data["prev_close"] * self.data["shares"]
            self.data["calc_market_cap"] = calc_market_cap

            print("\n===== 계산된 시가총액 =====")
            print("전일종가 × 상장주식수 =", calc_market_cap)

            print("\n===== 비교 결과 =====")
            diff = abs(calc_market_cap - self.data["market_cap_opt10001"])
            print("차이:", diff)

            if diff < 10_000_000_000:  # 100억 이하 차이면 사실상 동일
                print("결론: ✔ 시가총액 계산 정확함")
            else:
                print("결론: ❗ opt10001 시가총액과 차이가 큼 (opt10001 값이 부정확할 가능성 높음)")

            print("========================")
            QApplication.instance().quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    test = KiwoomTest()
    sys.exit(app.exec_())
