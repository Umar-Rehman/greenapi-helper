from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox, QStyleFactory

class ChatHistoryDialog(QDialog):
    def __init__(self, parent=None, chat_id_default="", count_default=10):
        super().__init__(parent)
        self.setWindowTitle("Get Chat History")
        self.setStyle(QStyleFactory.create("Fusion"))
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.chat_id = QLineEdit(chat_id_default)
        self.chat_id.setPlaceholderText("e.g. 7987...@c.us or 1203...@g.us")
        layout.addRow("chatId:", self.chat_id)

        self.count = QSpinBox()
        self.count.setRange(1, 1000)
        self.count.setSingleStep(10)
        self.count.setValue(count_default)
        layout.addRow("count:", self.count)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return self.chat_id.text().strip(), int(self.count.value())


class GetMessageDialog(QDialog):
    def __init__(self, parent=None, chat_id_default=""):
        super().__init__(parent)
        self.setWindowTitle("Get Message")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.chat_id = QLineEdit(chat_id_default)
        self.chat_id.setPlaceholderText("e.g. 7987...@c.us or 1203...@g.us")
        layout.addRow("chatId:", self.chat_id)

        self.id_message = QLineEdit()
        self.id_message.setPlaceholderText("e.g. BAE5F4886F6F2D05")
        layout.addRow("idMessage:", self.id_message)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return self.chat_id.text().strip(), self.id_message.text().strip()
