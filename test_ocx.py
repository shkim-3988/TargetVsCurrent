import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QTimer

def test():
    print("1. QAxWidget 생성 시도...")
    try:
        ocx = QAxWidget(window)
        print("2. QAxWidget 생성 성공")
        ocx.setControl("KHOPENAPI.KHOpenAPICtrl.1")
        print("3. setControl 성공 → OCX 정상")
    except Exception as e:
        print(f"오류: {e}")
    finally:
        app.quit()

app = QApplication(sys.argv)
window = QWidget()
window.setLayout(QVBoxLayout())
window.show()
QTimer.singleShot(1000, test)
sys.exit(app.exec_())