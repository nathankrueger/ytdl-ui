import sys
import os

from typing import override, Callable
from enum import Enum
from PyQt6.QtGui import QFontMetrics, QBrush, QColor, QAction
from PyQt6.QtCore import (
    Qt,
    QAbstractTableModel,
    QVariant,
    QModelIndex,
    QItemSelectionModel,
    QSortFilterProxyModel,
    QTimer
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QGridLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QCheckBox,
    QTableView,
    QHeaderView,
    QMenu,
    QSizePolicy,
    QFileDialog
)

from cfg_file import YtDlConfig
from ytdlp_process import YtDlpProcess, YtDlpInfo, YtDlpListener
from util import (
    not_blank,
    bytes_human_readable,
    bytes_per_sec_human_readable,
    seconds_human_readable,
    shutdown,
)

CFG_FILE = 'cfg.json'

MIN_HEIGHT_POLICY = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
EXPAND_ALL_POLICY = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

def get_one_line_textbox():
    text_edit = QTextEdit(sizePolicy=MIN_HEIGHT_POLICY)
    font_metrics = QFontMetrics(text_edit.font())
    text_edit.setFixedHeight(font_metrics.lineSpacing() + 10)
    text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    text_edit.setAcceptRichText(False)
    return text_edit

class YtDlColumn(Enum):
    PROGRESS = 0
    URL = 1
    SIZE = 2
    SPEED = 3
    ETA = 4

    @staticmethod
    def get_column_names() -> list[str]:
        result = []
        for val in YtDlColumn:
            result.append(val.get_name())
        return result
    
    @staticmethod
    def get_column_count() -> int:
        return len(YtDlColumn.get_column_names())
    
    @staticmethod
    def get_sort_function(column: int) -> Callable[[YtDlpInfo, YtDlpInfo], bool]:
        return lambda x, y: YtDlColumn.get_raw_data_row(x)[column] < YtDlColumn.get_raw_data_row(y)[column]

    @staticmethod
    def get_raw_data_row(info: YtDlpInfo) -> tuple:
        assert info is not None
        return (
            info.progress,
            info.url,
            info.size_bytes,
            info.rate_bytes_per_sec,
            info.eta_seconds
        )
    
    @staticmethod
    def get_formatted_data_row(info: YtDlpInfo) -> tuple:
        return (
            info.progress,
            info.url,
            bytes_human_readable(info.size_bytes),
            bytes_per_sec_human_readable(info.rate_bytes_per_sec),
            seconds_human_readable(info.eta_seconds)
        )
    
    @staticmethod
    def get_default_data_row(url: str) -> tuple:
        return ("0.0", url, "-", "-", "-")

    def get_index(self) -> int:
        return self.value
    
    def get_name(self) -> str:
        return self.name.upper()[0] + self.name.lower()[1:]

class YtDlTableItem(YtDlpListener):
    def __init__(self, url: str, model_row: int, table_model, download_dir: str = None):
        self.url = url
        self.download_dir = download_dir
        self.proc: YtDlpProcess = YtDlpProcess(url, download_dir)
        self.proc.add_listener(self)
        self.model_row = model_row
        self.table_model = table_model
    
    def add_listener(self, listener: YtDlpListener):
        self.proc.add_listener(listener)

    def download(self):
        self.proc.download()

    def is_complete(self) -> bool:
        return self.proc.is_complete()
    
    def get_rc(self) -> int | None:
        return self.proc.get_rc()
    
    def get_ytdl_info(self) -> YtDlpInfo:
        return self.proc.get_info()

    def get_data_row(self) -> tuple:
        if (info := self.get_ytdl_info()) is not None:
            return YtDlColumn.get_formatted_data_row(info)
        else:
            return YtDlColumn.get_default_data_row(self.url)

    def update_row_in_table_model(self):
        # update the row in question
        self.table_model.dataChanged.emit(
            self.table_model.index(self.model_row, 0),
            self.table_model.index(self.model_row, YtDlColumn.get_column_count() - 1)
        )

    @override
    def status_update(self, info: YtDlpInfo):
        self.update_row_in_table_model()

    @override
    def completed(self, rc: int):
        self.update_row_in_table_model()

class YtDlSortModelProxy(QSortFilterProxyModel):
    @override
    def lessThan(self, left: QModelIndex, right: QModelIndex):
        assert left.column() == right.column()
        left_item: YtDlTableItem = self.sourceModel().get_item(left.row())
        right_item: YtDlTableItem = self.sourceModel().get_item(right.row())
        left_info = left_item.get_ytdl_info()
        right_info = right_item.get_ytdl_info()
        sort_fn = YtDlColumn.get_sort_function(left.column())
        return sort_fn(left_info, right_info)

class YtDlTableModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self.data: list[YtDlTableItem] = list() if data is None else data
        self.headers = YtDlColumn.get_column_names()

    @override
    def rowCount(self, index) -> int:
        return len(self.data)
    
    @override
    def columnCount(self, index) -> int:
        return len(self.headers) if len(self.data) > 0 else 0

    @override
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        item = self.data[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if item.is_complete():
                data = list(item.get_data_row())
                data[YtDlColumn.ETA.get_index()] = "00:00"
                return data[index.column()]
            else:
                return item.get_data_row()[index.column()]
        elif role == Qt.ItemDataRole.BackgroundRole:
            if item.is_complete():
                # green if rc == 0, else red
                return QVariant(QBrush(QColor("#66ff99"))) if item.get_rc() == 0 else QVariant(QBrush(QColor("#ff4d4d")))
            else:
                # white, unchanged
                return QVariant(QBrush(QColor("white")))

        return None

    @override
    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.headers[section]
            else:
                return str(section + 1)
        return QVariant()

    def refresh_ui(self):
        self.layoutChanged.emit()
    
    def add_item(self, item: YtDlTableItem):
        self.data.append(item)
        self.refresh_ui()

    def get_item(self, row: int) -> YtDlTableItem | None:
        if row >= 0 and row < len(self.data):
            return self.data[row]
        return None
    
    def get_all_items(self) -> list[YtDlTableItem]:
        result = []
        for row in range(self.rowCount(None)):
            result.append(self.get_item(row))
        return result
    
    def clear_completed(self):
        to_remove = []
        for item in self.data:
            if item.is_complete():
                to_remove.append(item)

        for item in to_remove:
            self.data.remove(item)
        
        self.refresh_ui()

class BlinkingRedCheckbox(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.red_val = 0
        self.count_up = True
        self.enabled_cb = lambda: False
        self.timer = QTimer()
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.timer_callback)
        self.timer.start()

    def set_enabled_callback(self, enabled_callback: Callable[[], bool]):
        self.enabled_cb = enabled_callback

    def timer_callback(self):
        delta = 10
        max_red_val = 255

        if (not self.checkState() == Qt.CheckState.Checked) or (not self.enabled_cb()):
            self.setStyleSheet('QCheckBox {color: black;}')
            return
        
        if self.count_up:
            if self.red_val + delta > max_red_val:
                self.red_val = max_red_val
                self.count_up = False
            else:
                self.red_val += delta
        else:
            if self.red_val - delta < 0:
                self.red_val = 0
                self.count_up = True
            else:
                self.red_val -= delta
        
        self.setStyleSheet(f"QCheckBox {{color: #{self.red_val:02x}0000;}}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ytdl-ui")

        # downloads table
        self.table = QTableView(sizePolicy=EXPAND_ALL_POLICY)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.setSortingEnabled(True)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table_model = YtDlTableModel()
        self.sorting_model = YtDlSortModelProxy()
        self.sorting_model.setSourceModel(self.table_model)
        self.table.setModel(self.sorting_model)
        
        # download label
        self.download_dir_label = QLabel(text="Download Dir:")

        # download btn
        self.download_btn = QPushButton(text="Download")
        self.download_btn.clicked.connect(self.download_btn_callback)

        # download URL textbox
        self.url_textbox = get_one_line_textbox()

        # download directory textbox
        self.download_dir_textbox = get_one_line_textbox()

        # choose directory button
        self.choose_dir_btn = QPushButton(text="...")
        self.choose_dir_btn.clicked.connect(self.choose_download_dir)
        self.choose_dir_btn.setFixedWidth(50)

        # clear completed button
        self.clear_completed_btn = QPushButton(text="Clear Completed")
        self.clear_completed_btn.clicked.connect(self.table_model.clear_completed)

        # overall statistics label
        self.overall_stats_label = QLabel(text="Overall Statistics")
        self.overall_stats_timer = QTimer()
        self.overall_stats_timer.setInterval(250)
        self.overall_stats_timer.timeout.connect(self.overall_stats_timer_callback)
        self.overall_stats_timer.start()

        # shutdown upon completion
        self.shutdown_checkbox = BlinkingRedCheckbox(text="Shutdown upon completion")
        self.shutdown_checkbox.set_enabled_callback(lambda: len(self.table_model.get_all_items()) > 0)

        # QGridLayout::addWidget(widget: QWidget, row: int, column: int, rowSpan: int, columnSpan: int, alignment: QtCore.Qt.AlignmentFlag)
        self.grid_layout = QGridLayout()
        self.grid_layout.addWidget(self.download_dir_label, 0, 0)
        self.grid_layout.addWidget(self.download_dir_textbox, 0, 1)
        self.grid_layout.addWidget(self.choose_dir_btn, 0, 2)
        self.grid_layout.addWidget(self.download_btn, 1, 0)
        self.grid_layout.addWidget(self.url_textbox, 1, 1, 1, 2)
        self.grid_layout.addWidget(self.table, 2, 0, 1, 3)
        self.grid_layout.addWidget(self.clear_completed_btn, 3, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid_layout.addWidget(self.overall_stats_label, 4, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        self.grid_layout.addWidget(self.shutdown_checkbox, 4, 2, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        # create the top-level widget for the window frame
        widget = QWidget()
        widget.setLayout(self.grid_layout)
        self.setCentralWidget(widget)

    def _resize_columns(self):
        resizable_columns = [
            YtDlColumn.PROGRESS.get_index(),
            YtDlColumn.SIZE.get_index(),
            YtDlColumn.SPEED.get_index(),
            YtDlColumn.ETA.get_index()
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
            item = self.table_model.get_item(self.sorting_model.mapToSource(row).row())
            item.proc.kill()
            self.table.selectionModel().select(row, QItemSelectionModel.SelectionFlag.Clear)

    def add_download(self, url: str, download_dir: str):
        if not_blank(url):
            table_item = YtDlTableItem(url=url, model_row=self.table_model.rowCount(None), table_model=self.table_model, download_dir=download_dir)
            table_item.download()
            self.table_model.add_item(table_item)
            self._resize_columns()

    def download_btn_callback(self):
        add_url = self.url_textbox.toPlainText()
        download_dir = self.download_dir_textbox.toPlainText()
        self.add_download(add_url, download_dir)
        self.url_textbox.setText(None)

    def choose_download_dir(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder_path:
            self.download_dir_textbox.setText(folder_path)

    def shutdown_if_all_completed(self):
        # nothing to do if the shutdown checkbox isn't checked
        if not self.shutdown_checkbox.checkState() == Qt.CheckState.Checked:
            return

        # if there are no items in the table, don't shutdown
        items = self.table_model.get_all_items()
        if len(items) < 1:
            return

        # how many downloads are in progress?
        num_active = 0
        for item in items:
            if not item.get_ytdl_info().completed:
                num_active += 1

        # if there are items, but all are complete, it's time to shutdown
        if num_active == 0:
            shutdown()

    def overall_stats_timer_callback(self):
        items = self.table_model.get_all_items()
        total_bytes_per_sec: float = 0.0
        total_active_downloads: int = 0
        eta_for_last_download: int = 0

        self.shutdown_if_all_completed()

        for item in items:
            info = item.get_ytdl_info()
            if not info.completed:
                total_bytes_per_sec += info.rate_bytes_per_sec
                eta_for_last_download = max(eta_for_last_download, info.eta_seconds)
                total_active_downloads += 1

        self.overall_stats_label.setText(f"<h3>Overall Statistics</h3>\n  <b>Total Rate:</b> {bytes_per_sec_human_readable(total_bytes_per_sec)}\n  <b>ETA for last download:</b> {seconds_human_readable(eta_for_last_download)}\n  <b>Active Downloads:</b> {total_active_downloads}")

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        window.resize(800, 600)

        if os.path.exists(CFG_FILE):
            cfg: YtDlConfig = YtDlConfig.get_cfg(CFG_FILE)
            if cfg.download_dir is not None:
                window.download_dir_textbox.setText(cfg.download_dir)
            if cfg.files is not None:
                for file in cfg.files:
                    window.add_download(file, window.download_dir_textbox.toPlainText())

        window.show()
        app.exec()
    except Exception as e:
        print(e)