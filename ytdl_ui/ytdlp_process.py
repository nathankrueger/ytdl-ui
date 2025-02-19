import re
from subprocess import Popen, PIPE
from copy import deepcopy
from threading import Thread, Lock
from time import sleep
from dataclasses import dataclass
from typing import override, Self
from PyQt6.QtCore import QThread, pyqtSignal
from threading import Condition

from util import dbg_print, not_blank, ensure_directory

def run_command(command: list) -> tuple[bool, str]:
    process = Popen(command, stdout=PIPE, stderr=PIPE, text=True)
    stdout, stderr = process.communicate()
    success = process.returncode == 0
    return success, stdout

@dataclass
class YtDlpInfo:
    url: str
    progress: float
    rate_bytes_per_sec: int
    size_bytes: int
    eta_seconds: int
    completed: bool

    @staticmethod
    def new(url: str) -> Self:
        return YtDlpInfo(url, 0.0, 0, 0, 0, False)
    
    def clone(self):
        return deepcopy(self)

class YtDlpListener:
    def status_update(self, info: YtDlpInfo):
        """
        Override me
        """

        pass
    
    def completed(self, rc: int):
        """
        Override me
        """

        pass

class YtDlpProcess:
    MAX_RETRIES = 1024

    def __init__(self, url: str, output_folder: str = None):
        self.url: str = url
        self.process: Popen = None
        self.proc_lock: Lock = Lock()
        self.cancelled: bool = False
        self.download_thread = None
        self.output_folder = output_folder

        # guards access to 'ytdlp_info', 'rc', 'listeners'
        self.data_lock = Lock()
        self.rc: int = None
        self.ytdlp_info = YtDlpInfo.new(self.url)
        self.formats: list[tuple[str,str]] = []
        self.listeners: list[YtDlpListener] = []

    @staticmethod
    def parse_byte_size(s: str) -> int | None:
        if s.endswith("GiB"):
            return int(float(s[:-3]) * 1024.0**3)
        elif s.endswith("MiB"):
            return int(float(s[:-3]) * 1024.0**2)
        elif s.endswith("KiB"):
            return int(float(s[:-3]) * 1024.0**1)
        elif s.endswith("B"):
            return int(float(s[:-1]) * 1024.0**0)
        return 0

    @staticmethod
    def parse_seconds(s: str) -> int | None:
        if "--" in s:
            return None
        parts = s.split(':')
        match len(parts):
            case 2:
                return (int(parts[0]) * 60**1) + (int(parts[1]) * 60**0)
            case 3:
                return (int(parts[0]) * 60**2) + (int(parts[1]) * 60**1) + (int(parts[0]) * 60**0)
            case _:
                return 0

    def _download_func(self, format: str = None):
        # determine what format to use
        if format is None:
            # default is to choose best mp4, otherwise best video available
            #   (see: https://man.archlinux.org/man/extra/yt-dlp/yt-dlp.1.en)
            vid_fmt = "bestvideo*+bestaudio/best"
        else:
            vid_fmt = format

        # create the yt-dlp process
        with self.proc_lock:
            ytdlp_args = ['yt-dlp', self.url, '-R', str(YtDlpProcess.MAX_RETRIES), '-f', vid_fmt]
            if not_blank(self.output_folder):
                ensure_directory(self.output_folder)
                ytdlp_args += ['-o', f'{self.output_folder}/%(title)s.%(ext)s']

            dbg_print(" ".join(ytdlp_args))
            self.process = Popen(args=ytdlp_args, stdout=PIPE, stderr=PIPE, text=True)

        # run the process, reading output one line at a time and keeping track of the progression of the download
        while not self.cancelled:
            output = self.process.stdout.readline()
            if output == '' and self.process.poll() is not None:
                break
            else:
                self.parse_output(output.strip())
                if self.ytdlp_info is not None:
                    self.notify_listeners()

        # determine success of process
        self.rc = self.process.poll()

        # set some details that may not get parsed above
        with self.data_lock:
            if self.rc == 0:
                self.ytdlp_info.progress = 100.0
            self.ytdlp_info.completed = True
            self.ytdlp_info.rate_bytes_per_sec = 0
            self.ytdlp_info.eta_seconds = 0
        
        self.notify_listeners()
        self.download_thread = None

    def determine_formats(self):
        success, stdout = run_command(['yt-dlp', '-S', 'hasvid,vext,bitrate', '-F', self.url])
        stdout = stdout.replace('\\n', '\n')
        if success:
            self.formats = []
            record_format = False
            for line in stdout.split('\n'):
                if '---' in line:
                    record_format = True
                    continue
                if record_format:
                    split_line = line.split()
                    if len(split_line) > 0:
                        self.formats.append(split_line[0], line)

    def add_listener(self, listener: YtDlpListener):
        with self.data_lock: self.listeners.append(listener)

    def remove_listener(self, listener: YtDlpListener):
        with self.data_lock: self.listeners.remove(listener)

    def get_info(self) -> YtDlpInfo:
        with self.data_lock: return self.ytdlp_info.clone()

    def download(self, format: str = None):
        if self.download_thread is None:
            self.cancelled = False
            self.rc = None
            self.download_thread = Thread(target=self._download_func, args=[format], daemon=True).start()
        else:
            raise Exception(f"Already downloading: {self.url}")

    def notify_listeners(self):
        with self.data_lock:
            for listener in self.listeners:
                listener.status_update(self.ytdlp_info)
                if self.ytdlp_info.completed:
                    listener.completed(self.rc)

    def parse_output(self, output: str):
        if (vid_match := re.search(r'\[download\]\s+(\d+\.\d+)%\s+of\s+~?\s+(\d+\.\d+(?:GiB|MiB|GiB|B))\s+at\s+(\d+\.\d+(?:GiB|MiB|KiB|B))\/s\s+ETA\s+([0-9:]+)', output)):
            with self.data_lock:
                self.ytdlp_info = YtDlpInfo(
                    url=self.url,
                    progress=float(vid_match.group(1)),
                    size_bytes=YtDlpProcess.parse_byte_size(vid_match.group(2)),
                    rate_bytes_per_sec=YtDlpProcess.parse_byte_size(vid_match.group(3)),
                    eta_seconds=YtDlpProcess.parse_seconds(vid_match.group(4)),
                    completed=False
                )
        
    def get_formats(self):
        return self.formats

    def kill(self):
        self.cancelled = True
        with self.proc_lock:
            if self.process is not None:
                self.process.kill()

    def is_complete(self):
        with self.data_lock: return self.rc is not None
    
    def get_rc(self):
        with self.data_lock: return self.rc

class YtDlpQThread(QThread, YtDlpListener):
    status_update_signal = pyqtSignal(YtDlpInfo)
    completed_signal = pyqtSignal(int)

    def __init__(self, url: str, output_folder: str, parent=None):
        super().__init__(parent)
        self.proc = YtDlpProcess(url, output_folder)
        self.proc.add_listener(self)
        self.cancelled = False
        self.condition = Condition()
        self.rc = None
        self.info = None

    def download(self, format: str = None):
        self.proc.download(format)

    def kill(self):
        self.proc.kill()

    @override
    def status_update(self, info: YtDlpInfo):
        with self.condition:
            self.info = info.clone()
            self.condition.notify()

    @override
    def completed(self, rc: int):
        with self.condition:
            self.rc = rc
            self.cancelled = True
            self.condition.notify()

    def run(self):
        while not self.cancelled:
            with self.condition:
                self.condition.wait()
                if self.rc != None:
                    self.completed_signal.emit(self.rc)
                if self.info != None:
                    self.status_update_signal.emit(self.info)
                self.rc = None
                self.info = None

if __name__ == '__main__':
    ytdlp_proc = YtDlpProcess("https://www.youtube.com/watch?v=6uMNnZtIS6s", "test")
    class ExampleListener(YtDlpListener):
        @override
        def status_update(self, info: YtDlpInfo):
            print(f"Status update for: {info.url}  ({info.size_bytes / 1.0e6:.02f} MB)")
            print(f"\tProgress: {info.progress}%")
            print(f"\tETA (s): {info.eta_seconds}")
            print(f"\t: {float(info.rate_bytes_per_sec) / 1.0e6:02f} MB/s")
        
        @override
        def completed(self, rc: int):
            print(f"yt-dlp has completed with rc: {rc}")

    ytdlp_proc.add_listener(ExampleListener())
    ytdlp_proc.download()

    try:
        while not ytdlp_proc.is_complete():
            sleep(0.5)
    except KeyboardInterrupt:
        pass

    if not ytdlp_proc.is_complete():
        ytdlp_proc.kill()
