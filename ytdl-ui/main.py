import sys

from typing import override
from enum import Enum
from PyQt6.QtCore import Qt, QAbstractTableModel, QVariant, QItemSelectionModel
from PyQt6.QtGui import QFontMetrics, QBrush, QColor, QAction
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
    QMenu,
    QSizePolicy
)

from ytdlp_process import YtDlpProcess, YtDlpInfo, YtDlpListener
from util import (
    not_blank,
    bytes_human_readable,
    bytes_per_sec_human_readable,
    seconds_human_readable
) 

MIN_HEIGHT_POLICY = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
EXPAND_ALL_POLICY = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

def get_one_line_textbox():
    text_edit = QTextEdit(sizePolicy=MIN_HEIGHT_POLICY)
    font_metrics = QFontMetrics(text_edit.font())
    text_edit.setFixedHeight(font_metrics.lineSpacing() + 10)
    text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    text_edit.setAcceptRichText(False)
    return text_edit

class YtDlColumHeader(Enum):
    PROGRESS = 0
    URL = 1
    SIZE = 2
    SPEED = 3
    ETA = 4

    @staticmethod
    def get_column_names() -> list[str]:
        result = []
        for val in YtDlColumHeader:
            result.append(val.get_name())
        return result

    def get_index(self) -> int:
        return self.value
    
    def get_name(self) -> str:
        return self.name.upper()[0] + self.name.lower()[1:]

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
            return (
                info.progress,
                info.url,
                bytes_human_readable(info.size_bytes),
                bytes_per_sec_human_readable(info.rate_bytes_per_sec),
                seconds_human_readable(info.eta_seconds)
            )
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
        self.headers = YtDlColumHeader.get_column_names()

    def rowCount(self, index) -> int:
        return len(self.data)
    
    def columnCount(self, index) -> int:
        return len(self.headers) if len(self.data) > 0 else 0
    
    def refresh_ui(self):
        self.layoutChanged.emit()
    
    def add_item(self, item: YtDlTableItem):
        self.data.append(item)
        self.refresh_ui()

    def get_item(self, row: int):
        if row >= 0 and row < len(self.data):
            return self.data[row]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        item = self.data[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if item.is_complete():
                data = list(item.get_data())
                data[YtDlColumHeader.ETA.get_index()] = "00:00"
                return data[index.column()]
            else:
                return item.get_data()[index.column()]
        elif role == Qt.ItemDataRole.BackgroundRole:
            if item.is_complete():
                # green if rc == 0, else red
                return QVariant(QBrush(QColor("#66ff99"))) if item.get_rc() == 0 else QVariant(QBrush(QColor("#ff4d4d")))
            else:
                # white, unchanged
                return QVariant(QBrush(QColor("white")))

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
        
        self.refresh_ui()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ytdl-ui")
        self.grid_layout = QGridLayout()

        # downloads table
        self.table = QTableView(sizePolicy=EXPAND_ALL_POLICY)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table_model = YtDlTableModel()
        self.table_listener = YtDlTableListener(self.table_model)
        self.table.setModel(self.table_model)
        
        # download label
        self.download_dir_label = QLabel(text="Download Dir:")

        # download btn
        self.download_btn = QPushButton(text='Download')
        self.download_btn.clicked.connect(self.download_btn_callback)

        # download URL textbox
        self.url_textbox = get_one_line_textbox()

        # download directory textbox
        self.download_dir_textbox = get_one_line_textbox()

        # clear completed button
        self.clear_completed_btn = QPushButton(text='Clear Completed')
        self.clear_completed_btn.clicked.connect(self.table_model.clear_completed)

        # overall statistics label
        self.overall_stats_label = QLabel(text="Overall Statistics:")

        # QGridLayout::addWidget(widget: QWidget, row: int, column: int, rowSpan: int, columnSpan: int, alignment: QtCore.Qt.AlignmentFlag)
        self.grid_layout.addWidget(self.download_dir_label, 0, 0)
        self.grid_layout.addWidget(self.download_dir_textbox, 0, 1)
        self.grid_layout.addWidget(self.download_btn, 1, 0)
        self.grid_layout.addWidget(self.url_textbox, 1, 1)
        self.grid_layout.addWidget(self.table, 2, 0, 1, 2)
        self.grid_layout.addWidget(self.clear_completed_btn, 3, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid_layout.addWidget(self.overall_stats_label, 4, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)

        # create the top-level widget for the window frame
        widget = QWidget()
        widget.setLayout(self.grid_layout)
        self.setCentralWidget(widget)

    def _resize_columns(self):
        resizable_columns = [
            YtDlColumHeader.PROGRESS.get_index(),
            YtDlColumHeader.SIZE.get_index(),
            YtDlColumHeader.SPEED.get_index(),
            YtDlColumHeader.ETA.get_index()
        ]
        for i in resizable_columns:
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

    def show_table_context_menu(self, pos):
        menu = QMenu(self)
        action = QAction("Cancel", self)
        action.triggered.connect(self.cancel_item)
        menu.addAction(action)

        # show the menu at the position of the right click
        menu.exec(self.table.mapToGlobal(pos))

    def cancel_item(self, item):
        for row in self.table.selectionModel().selectedRows():
            item = self.table_model.get_item(row.row())
            item.proc.kill()
            self.table.selectionModel().select(row, QItemSelectionModel.SelectionFlag.Clear)

    def download_btn_callback(self):
        add_url = self.url_textbox.toPlainText()
        download_dir = self.download_dir_textbox.toPlainText()
        if not_blank(add_url):
            table_item = YtDlTableItem(url=add_url, download_dir=download_dir)
            table_item.add_listener(self.table_listener)
            table_item.download()
            self.table_model.add_item(table_item)
            self._resize_columns()

app = QApplication(sys.argv)
window = MainWindow()
window.resize(640, 480)
window.show()
app.exec()