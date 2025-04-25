from PySide6 import QtWidgets
from PySide6.QtCore import QThread, Signal

from videotrans import tts
from videotrans.configure import config
from videotrans.util import tools


def openwin():
    class TestTTS(QThread):
        uito = Signal(str)

        def __init__(self, *, parent=None, text=None, role=None):
            super().__init__(parent=parent)
            self.text = text
            self.role = role

        def run(self):
            try:
                tts.run(
                    queue_tts=[{"text": self.text, "role": self.role,
                                "filename": config.TEMP_HOME + "/testsparktts.mp3", "tts_type": tts.SPARK_TTS}],
                    language="zh",
                    play=True,
                    is_test=True
                )
                self.uito.emit("ok")
            except Exception as e:
                self.uito.emit(str(e))

    def feed(d):
        if d == "ok":
            QtWidgets.QMessageBox.information(winobj, "ok", "Test Ok")
        else:
            QtWidgets.QMessageBox.critical(winobj, config.transobj['anerror'], d)
        winobj.test.setText('测试api')

    def test():
        url = winobj.api_url.text().strip()
        if tools.check_local_api(url) is not True:
            return        
        if not url.startswith('http'):
            url = 'http://' + url
        config.params["sparktts_url"] = url
        task = TestTTS(parent=winobj,
                       text="你好啊我的朋友",
                       role="中文女")
        winobj.test.setText('测试中请稍等...')
        task.uito.connect(feed)
        task.start()

    def save():
        url = winobj.api_url.text().strip()
        if tools.check_local_api(url) is not True:
            return
        if not url.startswith('http'):
            url = 'http://' + url
        role = winobj.role.toPlainText().strip()

        config.params["sparktts_url"] = url

        config.params["sparktts_role"] = role
        config.getset_params(config.params)
        tools.set_process(text='sparktts', type="refreshtts")

        winobj.close()

    from videotrans.component import sparkttsForm
    winobj = config.child_forms.get('sparkttsw')
    if winobj is not None:
        winobj.show()
        winobj.raise_()
        winobj.activateWindow()
        return
    winobj = sparkttsForm()
    config.child_forms['sparkttsw'] = winobj
    if config.params["sparktts_url"]:
        winobj.api_url.setText(config.params["sparktts_url"])
    if config.params["sparktts_role"]:
        winobj.role.setPlainText(config.params["sparktts_role"])

    winobj.save.clicked.connect(save)
    winobj.test.clicked.connect(test)
    winobj.show()
