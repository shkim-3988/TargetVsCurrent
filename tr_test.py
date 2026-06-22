import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop


class KiwoomTest(QAxWidget):
    def __init__(self):
        super().__init__()
        self.setControl("KHOPENAPI.KHOpenAPICtrl.1")

        self.login_event_loop = QEventLoop()
        self.tr_event_loop = QEventLoop()

        self.OnEventConnect.connect(self.on_login)
        self.OnReceiveTrData.connect(self.on_tr_data)

        print("로그인 시도 중...")
        self.dynamicCall("CommConnect()")
        self.login_event_loop.exec_()

        print("로그인 성공. opt10001 테스트 시작.")
        self.test_opt10001()

    def on_login(self, err_code):
        if err_code == 0:
            print("로그인 성공")
        else:
            print(f"로그인 실패: {err_code}")
        self.login_event_loop.exit()

    def test_opt10001(self):
        # 삼성전자 테스트
        code = "005930"

        self.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        self.dynamicCall("CommRqData(QString, QString, int, QString)",
                         "테스트요청", "opt10001", 0, "0101")

        print("opt10001 요청 전송 완료. 응답 대기 중...")
        self.tr_event_loop.exec_()

    def on_tr_data(self, screen_no, rqname, trcode, recordname, prev_next):
        print("=== OnReceiveTrData 호출됨 ===")
        print(f"rqname: {rqname}")

        if rqname == "테스트요청":
            name = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "종목명"
            ).strip()

            current = self.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                trcode, rqname, 0, "현재가"
            ).strip()

            print(f"종목명: {name}")
            print(f"현재가: {current}")

            print("opt10001 응답 정상 수신 → 차단 아님")
            self.tr_event_loop.exit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    KiwoomTest()
    sys.exit(app.exec_())
