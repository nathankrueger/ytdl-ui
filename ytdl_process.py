import re
from subprocess import Popen, PIPE
from threading import Thread, Lock
from time import sleep
from dataclasses import dataclass

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

class YtDlpConsumer:
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
        self.rc: int = None
        self.download_thread = None
        self.output_folder = output_folder

        self.data_lock = Lock()
        self.progress: float = 0.0
        self.rate_bytes_per_sec: int = 0
        self.size_bytes: int = 0
        self.eta_seconds: int = 0
        self.video_formats: list[str] = []
        self.listeners: list[YtDlpConsumer] = []

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
        return None

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
                return None

    def _download_func(self, video_format: str = None):
        if video_format is None:
            self.determine_video_formats()
            vid_fmt = self.video_formats[0]
        else:
            vid_fmt = video_format

        with self.proc_lock:
            output_args = []
            if self.output_folder:
                output_args = ['-o', f'{self.output_folder}/%(title)s.%(ext)s']
            self.process = Popen(args=['yt-dlp', self.url, '-R', str(YtDlpProcess.MAX_RETRIES), '-f', vid_fmt] + output_args, stdout=PIPE, stderr=PIPE, text=True)

        while not self.cancelled:
            output = self.process.stdout.readline()
            if output == '' and self.process.poll() is not None:
                break
            else:
                self.parse_output(output.strip())

        self.rc = self.process.poll()
        self.download_thread = None

    def determine_video_formats(self):
        success, stdout = run_command(['yt-dlp', '-F', self.url])
        stdout = stdout.replace('\\n', '\n')
        if success:
            self.video_formats = []
            for line in stdout.split('\n')[6:-1]:
                self.video_formats.append(line.split()[0])

    def download(self, video_format: str = None):
        if self.download_thread is None:
            self.cancelled = False
            self.rc = None
            self.download_thread = Thread(target=self._download_func, args=[video_format], daemon=True).start()
        else:
            raise Exception(f"Already downloading: {self.url}")

    def notify_listeners(self):
        with self.data_lock:
            for listener in self.listeners:
                pass

    def parse_output(self, output: str):
        with self.data_lock:
            if (vid_match := re.search(r'\[download\]\s+(\d+\.\d+)%\s+of\s+(\d+\.\d+(?:GiB|MiB|GiB|B))\s+at\s+(\d+\.\d+(?:GiB|MiB|KiB|B))\/s\s+ETA\s+(.+)$', output)):
                self.progress = float(vid_match.group(1))
                self.size_bytes = YtDlpProcess.parse_byte_size(vid_match.group(2))
                self.rate_bytes_per_sec = YtDlpProcess.parse_byte_size(vid_match.group(3))
                self.eta_seconds = YtDlpProcess.parse_seconds(vid_match.group(4))

    def get_progress(self) -> float:
        with self.data_lock:
            return self.progress
    
    def get_rate(self) -> int:
        with self.data_lock:
            return self.rate_bytes_per_sec
    
    def get_size(self) -> int:
        with self.data_lock:
            return self.size_bytes
    
    def get_eta(self) -> int:
        with self.data_lock:
            return self.eta_seconds
        
    def get_video_formats(self):
        return self.video_formats

    def kill(self):
        self.cancelled = True
        with self.proc_lock:
            if self.process is not None:
                self.process.kill()

    def is_complete(self):
        return self.rc is not None
    
    def get_rc(self):
        return self.rc

ytdl_proc = YtDlpProcess("https://www.youtube.com/watch?v=6uMNnZtIS6s", "test")
ytdl_proc.download()
sleep(5)

try:
    while not ytdl_proc.is_complete():
        print(ytdl_proc.get_progress())
        print(ytdl_proc.get_eta())
        print(ytdl_proc.get_rate())
        print(ytdl_proc.get_size())
        print()
        sleep(0.5)
except KeyboardInterrupt:
    pass

ytdl_proc.kill()
sleep(0.5)
print(f"Is complete: {ytdl_proc.is_complete()}")