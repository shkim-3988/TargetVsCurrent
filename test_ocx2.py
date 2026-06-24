# test_ocx2.py
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QTimer

print("=== 시작 ===")

def test():
    print("1. QAxWidget 생성 시도...")
    try:
        ocx = QAxWidget(window)
        print("2. QAxWidget 생성 성공")
        result = ocx.setControl("KHOPENAPI.KHOpenAPICtrl.1")
        print(f"3. setControl 결과: {result}")
        window.layout().addWidget(ocx)
        ocx.setVisible(False)
        print("4. 레이아웃 추가 성공 → OCX 정상")
    except Exception as e:
        print(f"오류: {e}")
    finally:
        print("5. 종료")
        app.quit()

print("QApplication 생성...")
app = QApplication(sys.argv)
print("QWidget 생성...")
window = QWidget()
window.setLayout(QVBoxLayout())
window.show()
print("타이머 시작 (3초)...")
QTimer.singleShot(3000, test)   # 1초 → 3초로 늘림
print("이벤트 루프 진입...")
sys.exit(app.exec_())
