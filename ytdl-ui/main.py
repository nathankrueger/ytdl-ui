import sys

from typing import override
from PyQt6.QtCore import Qt, QAbstractTableModel, QVariant
from PyQt6.QtGui import QFontMetrics, QBrush, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QGridLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QTableView,
    QHeaderView,
    QSizePolicy
)

from ytdlp_process import YtDlpProcess, YtDlpInfo, YtDlpListener
from util import not_blank

MIN_HEIGHT_POLICY = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
EXPAND_ALL_POLICY = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

def get_one_line_textbox():
    text_edit = QTextEdit(sizePolicy=MIN_HEIGHT_POLICY)
    font_metrics = QFontMetrics(text_edit.font())
    text_edit.setFixedHeight(font_metrics.lineSpacing() + 10)
    text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    text_edit.setAcceptRichText(False)
    return text_edit

class YtDlTableItem:
    def __init__(self, url: str, download_dir: str = None):
        self.url = url
        self.download_dir = download_dir
        self.proc: YtDlpProcess = YtDlpProcess(url, download_dir)
    
    def add_listener(self, listener: YtDlpListener):
        self.proc.add_listener(listener)

    def download(self):
        self.proc.download()

    def is_complete(self) -> bool:
        return self.proc.is_complete()
    
    def get_rc(self) -> int | None:
        return self.proc.get_rc()

    def get_data(self) -> tuple:
        info = self.proc.get_info()
        if info is not None:
            return (info.progress, info.url, info.size_bytes, info.rate_bytes_per_sec, info.eta_seconds)
        else:
            return ("0.0", self.url, "-", "-", "-")
    
class YtDlTableListener(YtDlpListener):
    def __init__(self, table_model: QAbstractTableModel):
        self.table_model = table_model

    @override
    def status_update(self, info: YtDlpInfo):
        self.table_model.layoutChanged.emit()

    @override
    def completed(self, rc: int):
        self.table_model.layoutChanged.emit()

class YtDlTableModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self.data: list[YtDlTableItem] = list() if data is None else data
        self.headers = ["Progress", "URL", "Size", "Speed", "ETA"]

    def rowCount(self, index) -> int:
        return len(self.data)
    
    def columnCount(self, index) -> int:
        return len(self.headers) if len(self.data) > 0 else 0
    
    def add_item(self, item: YtDlTableItem):
        self.data.append(item)
        self.layoutChanged.emit()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        item = self.data[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return item.get_data()[index.column()]
        elif role == Qt.ItemDataRole.BackgroundRole:
            if not item.is_complete():
                # white, unchanged
                return QVariant(QBrush(QColor("white")))
            else:
                # green if rc == 0, else red
                return QVariant(QBrush(QColor("green"))) if item.get_rc() == 0 else QVariant(QBrush(QColor("red")))

        return None
    
    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.headers[section]
            else:
                return str(section + 1)
        
        return QVariant()
    
    def clear_completed(self):
        to_remove = []
        for item in self.data:
            if item.is_complete():
                to_remove.append(item)

        for item in to_remove:
            self.data.remove(item)
        
        self.layoutChanged.emit()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ytdl-ui")
        self.grid_layout = QGridLayout()

        # downloads table
        self.table = QTableView(sizePolicy=EXPAND_ALL_POLICY)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_model = YtDlTableModel()
        self.table_listener = YtDlTableListener(self.table_model)
        self.table.setModel(self.table_model)
        
        # download label
        self.download_dir_label = QLabel(text="Download Dir:")

        # add btn
        self.add_btn = QPushButton(text='Add')
        self.add_btn.clicked.connect(self.add_btn_callback)

        # add URL textbox
        self.add_textbox = get_one_line_textbox()

        # downlaod directory textbox
        self.download_dir_textbox = get_one_line_textbox()

        # clear completed button
        self.clear_completed_btn = QPushButton(text='Clear Completed')
        self.clear_completed_btn.clicked.connect(self.table_model.clear_completed)

        # overall statistics label
        self.overall_stats_label = QLabel(text="Overall Statistics:")

        # QGridLayout::addWidget(widget: QWidget, row: int, column: int, rowSpan: int, columnSpan: int, alignment: QtCore.Qt.AlignmentFlag)
        self.grid_layout.addWidget(self.download_dir_label, 0, 0)
        self.grid_layout.addWidget(self.download_dir_textbox, 0, 1)
        self.grid_layout.addWidget(self.add_btn, 1, 0)
        self.grid_layout.addWidget(self.add_textbox, 1, 1)
        self.grid_layout.addWidget(self.table, 2, 0, 1, 2)
        self.grid_layout.addWidget(self.clear_completed_btn, 3, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid_layout.addWidget(self.overall_stats_label, 4, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)

        # create the top-level widget for the window frame
        widget = QWidget()
        widget.setLayout(self.grid_layout)
        self.setCentralWidget(widget)

    def _resize_columns(self):
        for i in [0,2,3,4]:
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def add_btn_callback(self):
        add_url = self.add_textbox.toPlainText()
        download_dir = self.download_dir_textbox.toPlainText()
        if not_blank(add_url):
            table_item = YtDlTableItem(url=add_url, download_dir=download_dir)
            table_item.add_listener(self.table_listener)
            table_item.download()
            self.table_model.add_item(table_item)
            self._resize_columns()

app = QApplication(sys.argv)
window = MainWindow()
window.setFixedSize(640, 480)
window.show()
app.exec()